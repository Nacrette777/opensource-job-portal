"""
GradBridge: publish one of a job seeker's Reactive Resume (RR) resumes.

Publishing takes a snapshot that recruiters can rely on:

1. Read the resume's JSON from RR with the job seeker's own access token and
   note its updatedAt.
2. Ask RR to render the PDF of the stored resume.
3. Read updatedAt again. If it moved, the resume was edited while the PDF was
   rendering, so the PDF may not match the JSON: start over (a few times).
4. Save both files to private storage, then the ResumeVersion row, then move
   the ResumePublication pointer, in that order. Any failure before the
   pointer moves leaves the previous publication in place, and files written
   for a failed attempt are removed.

Recruiter access follows the pointer only (see api/v1/recruiter/candidates).
"""

import hashlib
import json
import uuid

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils import timezone

from peeldb.models import ResumeAccountLink, ResumePublication, ResumeVersion

from .rr_client import HTTP_TIMEOUT, RRIntegrationError, get_access_token

PDF_TIMEOUT = 90  # RR loads its PDF renderer lazily; the first render is slow.
SNAPSHOT_ATTEMPTS = 3


def private_storage():
    """Storage for published files. Never mapped to a URL."""
    return FileSystemStorage(location=settings.GRADBRIDGE_PRIVATE_MEDIA_ROOT, base_url=None)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _rr_get(path, access_token, *, timeout=HTTP_TIMEOUT):
    try:
        return requests.get(
            f"{settings.RR_INTERNAL_URL}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RRIntegrationError(
            "rr_unreachable", "Reactive Resume could not be reached. Nothing was changed.", status=502
        ) from exc


def _connected_link(user):
    link = ResumeAccountLink.objects.filter(
        user=user, status=ResumeAccountLink.STATUS_CONNECTED
    ).first()
    if not link:
        raise RRIntegrationError(
            "not_connected", "Connect your Reactive Resume account first.", status=409
        )
    return link


def list_rr_resumes(user):
    """The resumes in the job seeker's linked RR account, newest first."""
    _connected_link(user)
    response = _rr_get("/api/openapi/resumes", get_access_token(user))
    if response.status_code != 200:
        raise RRIntegrationError(
            "rr_api_failed", "Reactive Resume did not list your resumes.", status=502
        )
    return [
        {"id": r.get("id"), "name": r.get("name") or "", "updated_at": r.get("updatedAt") or ""}
        for r in response.json()
    ]


def _fetch_resume(external_resume_id, access_token):
    response = _rr_get(f"/api/openapi/resumes/{external_resume_id}", access_token)
    if response.status_code == 404:
        raise RRIntegrationError(
            "resume_not_found", "That resume was not found in your Reactive Resume account.", status=404
        )
    if response.status_code != 200:
        raise RRIntegrationError(
            "rr_api_failed", "Reactive Resume did not return the resume.", status=502
        )
    body = response.json()
    if not body.get("updatedAt") or "data" not in body:
        raise RRIntegrationError(
            "rr_api_failed", "Reactive Resume returned an incomplete resume.", status=502
        )
    return body


def _fetch_pdf(external_resume_id, access_token):
    response = _rr_get(
        f"/api/openapi/resumes/{external_resume_id}/pdf", access_token, timeout=PDF_TIMEOUT
    )
    if response.status_code != 200 or not response.content.startswith(b"%PDF"):
        raise RRIntegrationError(
            "pdf_failed", "Reactive Resume could not produce the PDF. Nothing was changed.", status=502
        )
    return response.content


def preview_pdf(user, external_resume_id):
    """The PDF RR renders for the job seeker's resume right now, for a look
    before publishing. Nothing is stored; RR only returns the job seeker's own
    resumes, because the request carries their own access token."""
    _connected_link(user)
    access_token = get_access_token(user)
    _fetch_resume(external_resume_id, access_token)  # 404 for any other resume
    return _fetch_pdf(external_resume_id, access_token)


def _snapshot(external_resume_id, access_token):
    """JSON + PDF of the same stored state of the resume."""
    for _attempt in range(SNAPSHOT_ATTEMPTS):
        before = _fetch_resume(external_resume_id, access_token)
        pdf = _fetch_pdf(external_resume_id, access_token)
        after = _fetch_resume(external_resume_id, access_token)
        if after["updatedAt"] == before["updatedAt"]:
            return before, pdf
    raise RRIntegrationError(
        "resume_changing",
        "The resume kept changing while it was being published. Finish editing, then publish again.",
        status=409,
    )


def publish(user, external_resume_id):
    """Snapshot an RR resume and make it the job seeker's published version."""
    link = _connected_link(user)
    access_token = get_access_token(user)
    resume, pdf = _snapshot(external_resume_id, access_token)

    data_bytes = json.dumps(
        {
            "external_resume_id": external_resume_id,
            "rr_user_id": link.rr_user_id,
            "name": resume.get("name") or "",
            "updatedAt": resume["updatedAt"],
            "data": resume["data"],
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    data_sha = _sha256(data_bytes)
    pdf_sha = _sha256(pdf)

    # Publishing the same unchanged resume again reuses its version.
    existing = ResumeVersion.objects.filter(
        user=user,
        rr_user_id=link.rr_user_id,
        external_resume_id=external_resume_id,
        rr_updated_at=resume["updatedAt"],
        data_sha256=data_sha,
    ).first()

    storage = private_storage()
    written = []
    try:
        if existing:
            version = existing
        else:
            version_id = uuid.uuid4()
            base = f"resumes/{user.id}/{version_id}"
            data_key = storage.save(f"{base}/resume.json", ContentFile(data_bytes))
            written.append(data_key)
            pdf_key = storage.save(f"{base}/resume.pdf", ContentFile(pdf))
            written.append(pdf_key)
            # Read back: the pointer must never reference a file that is not there.
            with storage.open(pdf_key, "rb") as fh:
                if _sha256(fh.read()) != pdf_sha:
                    raise RRIntegrationError(
                        "storage_failed", "The PDF could not be stored. Nothing was changed.", status=500
                    )
            version = None

        with transaction.atomic():
            if version is None:
                version = ResumeVersion.objects.create(
                    id=version_id,
                    user=user,
                    rr_user_id=link.rr_user_id,
                    external_resume_id=external_resume_id,
                    title=(resume.get("name") or "")[:255],
                    rr_updated_at=resume["updatedAt"],
                    data_key=data_key,
                    data_sha256=data_sha,
                    pdf_key=pdf_key,
                    pdf_sha256=pdf_sha,
                    pdf_size=len(pdf),
                )
            publication, _ = ResumePublication.objects.select_for_update().get_or_create(user=user)
            publication.version = version
            publication.published_at = timezone.now()
            publication.withdrawn_at = None
            publication.save()
    except RRIntegrationError:
        _remove(storage, written)
        raise
    except Exception as exc:
        _remove(storage, written)
        raise RRIntegrationError(
            "storage_failed", "The published files could not be saved. Nothing was changed.", status=500
        ) from exc
    return publication


def _remove(storage, keys):
    for key in keys:
        try:
            storage.delete(key)
        except OSError:
            pass


def withdraw(user):
    """Stop publishing. Versions are kept; recruiters lose access at once."""
    with transaction.atomic():
        publication, _ = ResumePublication.objects.select_for_update().get_or_create(user=user)
        if publication.version_id:
            publication.version = None
            publication.withdrawn_at = timezone.now()
            publication.save()
    return publication


def current_version(user):
    """The version recruiters may see for `user`, or None."""
    publication = ResumePublication.objects.filter(user=user).select_related("version").first()
    return publication.version if publication else None


def open_pdf(version):
    return private_storage().open(version.pdf_key, "rb")
