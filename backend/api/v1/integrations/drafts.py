"""
GradBridge: create a Reactive Resume (RR) draft from a job seeker's profile.

The profile is exported with peeldb.resume_export.build_json_resume() and sent
to RR's `POST /api/openapi/resumes/import/json-resume` with the job seeker's
own OAuth access token, so the draft lands in their RR account and RR's usual
ownership checks apply.

Each request is recorded first; its id is the requestId RR is idempotent on.
If RR created the draft but the response was lost, retrying the same request
returns that same draft instead of creating a second one. Two rules keep the
record honest when attempts overlap:

- The exported document is frozen on the first attempt and every retry sends
  that same document, so the draft and source_sha256 always match.
- A success is final. A slower attempt that fails afterwards must not mark the
  request failed; it returns the recorded success instead.
"""

import hashlib
import json

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from peeldb.models import ResumeAccountLink, ResumeIntegrationRequest
from peeldb.resume_export import build_json_resume

from .rr_client import HTTP_TIMEOUT, RRIntegrationError, get_access_token

IMPORT_PATH = "/api/openapi/resumes/import/json-resume"
SUCCEEDED = ResumeIntegrationRequest.STATUS_SUCCEEDED


def editor_url(external_resume_id):
    return f"{settings.RR_BASE_URL}/builder/{external_resume_id}"


def _fail(req, code, message, status=None):
    """Record a failed attempt, unless another attempt has already succeeded.

    Returns the succeeded request in that case (the caller should return it),
    otherwise the error for the caller to raise.
    """
    updated = (
        ResumeIntegrationRequest.objects.filter(pk=req.pk)
        .exclude(status=SUCCEEDED)
        .update(
            status=ResumeIntegrationRequest.STATUS_FAILED,
            error_code=code,
            error=message[:500],
            updated_at=timezone.now(),
        )
    )
    if not updated:
        return ResumeIntegrationRequest.objects.get(pk=req.pk)
    if status is None:
        status = 502 if code.startswith("rr_") else 400
    return RRIntegrationError(code, message, status=status)


def _outcome(result):
    if isinstance(result, ResumeIntegrationRequest):
        return result
    raise result


def _start_attempt(user, request_id, rr_user_id):
    """Create or lock the request, freeze its document, and count the attempt.

    The request is bound to the RR account linked on its first attempt. If the
    job seeker has since linked a different RR account, retrying would create
    a second draft there while the first may already exist in the old one, so
    that is refused and a new request is needed instead.

    Returns (request, already_succeeded).
    """
    with transaction.atomic():
        req, _created = ResumeIntegrationRequest.objects.select_for_update().get_or_create(
            id=request_id,
            defaults={"user": user, "kind": ResumeIntegrationRequest.KIND_CREATE_DRAFT},
        )
        if req.user_id != user.id:
            # Someone else's request id: answer as if it did not exist.
            raise RRIntegrationError("not_found", "Request not found.", status=404)
        if req.status == SUCCEEDED:
            return req, True
        if req.rr_user_id and req.rr_user_id != rr_user_id:
            raise RRIntegrationError(
                "rr_account_changed",
                "This request was started for a different Reactive Resume account. "
                "Create a new draft instead.",
                status=409,
            )
        req.rr_user_id = rr_user_id

        if not req.source_payload:
            export = build_json_resume(user)
            req.source_payload = export.data
            req.warnings = export.warnings
            body = json.dumps(export.data, ensure_ascii=False, sort_keys=True)
            req.source_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()

        req.attempts += 1
        req.status = ResumeIntegrationRequest.STATUS_PENDING
        req.error_code = ""
        req.error = ""
        req.save()
        return req, False


def create_draft(user, request_id):
    """Create (or, for a repeated request_id, return) the user's RR draft."""
    link = ResumeAccountLink.objects.filter(
        user=user, status=ResumeAccountLink.STATUS_CONNECTED
    ).first()
    if not link:
        raise RRIntegrationError(
            "not_connected", "Connect your Reactive Resume account first.", status=409
        )

    req, done = _start_attempt(user, request_id, link.rr_user_id or "")
    if done:
        return req

    try:
        access_token = get_access_token(user)
    except RRIntegrationError as exc:
        return _outcome(_fail(req, exc.code, exc.message, status=exc.status))

    # From the request, not the attempt, so every retry asks for the same name.
    name = f"GradBridge draft {req.created_at:%Y-%m-%d %H:%M}"
    try:
        response = requests.post(
            f"{settings.RR_INTERNAL_URL}{IMPORT_PATH}",
            json={"requestId": str(req.id), "name": name, "resume": req.source_payload},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        # RR may or may not have created it; a retry with this id is safe.
        return _outcome(
            _fail(req, "rr_unreachable", "Reactive Resume could not be reached. You can retry this request.")
        )

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code == 200 and payload.get("id"):
        # Success is final: written unconditionally. A concurrent attempt with
        # the same request id can only have received this same resume id.
        ResumeIntegrationRequest.objects.filter(pk=req.pk).update(
            status=SUCCEEDED,
            external_resume_id=payload["id"],
            error_code="",
            error="",
            updated_at=timezone.now(),
        )
        return ResumeIntegrationRequest.objects.get(pk=req.pk)

    if response.status_code == 400 and payload.get("code") == "INVALID_JSON_RESUME":
        return _outcome(
            _fail(
                req,
                "invalid_profile",
                "Reactive Resume could not read your profile as a resume: "
                + str(payload.get("message") or "unknown problem"),
            )
        )
    if response.status_code == 401:
        return _outcome(
            _fail(req, "rr_unauthorized", "Reactive Resume did not accept the authorization.")
        )
    return _outcome(
        _fail(req, "rr_import_failed", f"Reactive Resume rejected the draft ({response.status_code}).")
    )
