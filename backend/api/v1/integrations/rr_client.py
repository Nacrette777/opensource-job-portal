"""
GradBridge: talk to Reactive Resume (RR) on a job seeker's behalf.

RR is the OAuth authorization server. A job seeker links their own RR account
with the authorization-code flow + PKCE; we keep only their refresh token,
encrypted. Every call to RR mints a fresh access token from it and discards it:
RR's access tokens are self-contained JWTs that cannot be revoked early, so not
storing them means disconnecting leaves us holding nothing usable.

RR rotates the refresh token on every use and treats reuse of an old one as
theft (it kills the whole token family), so `get_access_token` refreshes under
a row lock and saves the new token in the same transaction.

Endpoint paths follow RR's `/.well-known/oauth-authorization-server`.
"""

import base64
import hashlib
import json
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from peeldb.models import ResumeAccountLink

SCOPES = "openid profile email offline_access"
AUTHORIZATION_TTL = timedelta(minutes=10)
HTTP_TIMEOUT = 10
# Waits before re-sending a refresh whose response was lost; all well inside
# RR's 60 s refresh-token reuse window.
REFRESH_RETRY_DELAYS = (2, 5)


class RRIntegrationError(Exception):
    """A failure the caller can show to the user. `code` is machine-readable."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def is_configured():
    return bool(
        settings.RR_OAUTH_CLIENT_ID
        and settings.RR_OAUTH_CLIENT_SECRET
        and settings.RR_TOKEN_ENCRYPTION_KEY
    )


def expected_issuer():
    return f"{settings.RR_BASE_URL}/api/auth"


def _endpoint(name):
    return f"{settings.RR_INTERNAL_URL}/api/auth/oauth2/{name}"


def _fernet():
    return Fernet(settings.RR_TOKEN_ENCRYPTION_KEY.encode())


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RRIntegrationError(
            "token_unreadable",
            "The stored Reactive Resume authorization could not be read. Please reconnect.",
            status=409,
        ) from exc


def _client_auth():
    return {
        "client_id": settings.RR_OAUTH_CLIENT_ID,
        "client_secret": settings.RR_OAUTH_CLIENT_SECRET,
    }


def _post_form(name, data):
    try:
        response = requests.post(
            _endpoint(name), data={**_client_auth(), **data}, timeout=HTTP_TIMEOUT
        )
    except requests.RequestException as exc:
        raise RRIntegrationError(
            "rr_unreachable", "Reactive Resume could not be reached.", status=502
        ) from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    return response.status_code, body


def start_authorization(user):
    """Record a fresh state + PKCE verifier for `user`; return RR's authorize URL."""
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(32)

    # Status is left alone: reconnecting must not drop a working link until the
    # new authorization actually succeeds.
    link, _created = ResumeAccountLink.objects.get_or_create(user=user)
    link.oauth_state = state
    link.oauth_code_verifier_encrypted = encrypt(verifier)
    link.oauth_started_at = timezone.now()
    link.save()

    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.RR_OAUTH_CLIENT_ID,
            "redirect_uri": settings.RR_OAUTH_REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            # Without `resource` RR may issue a token its own API rejects.
            "resource": settings.RR_BASE_URL,
            "prompt": "consent",
        }
    )
    return f"{settings.RR_BASE_URL}/api/auth/oauth2/authorize?{query}"


def _clear_pending(link):
    link.oauth_state = ""
    link.oauth_code_verifier_encrypted = ""
    link.oauth_started_at = None


def complete_authorization(user, *, code, state, iss, error=""):
    """Handle RR's redirect back to us and link the account named by `sub`."""
    link = ResumeAccountLink.objects.filter(user=user).first()
    if (
        not link
        or not link.oauth_state
        or not state
        or not secrets.compare_digest(link.oauth_state, state)
    ):
        raise RRIntegrationError(
            "invalid_state",
            "This authorization response does not match a request from your account. Please try connecting again.",
        )

    started_at = link.oauth_started_at
    verifier_encrypted = link.oauth_code_verifier_encrypted
    _clear_pending(link)  # single use, whatever happens next
    link.save()

    if error:
        raise RRIntegrationError(
            "authorization_denied", "Reactive Resume access was not granted."
        )
    if not started_at or timezone.now() - started_at > AUTHORIZATION_TTL:
        raise RRIntegrationError(
            "authorization_expired",
            "The connection request expired. Please try connecting again.",
        )
    if iss != expected_issuer():
        raise RRIntegrationError(
            "invalid_issuer",
            "The authorization response came from an unexpected issuer.",
        )
    if not code:
        raise RRIntegrationError("missing_code", "No authorization code was returned.")

    status_code, body = _post_form(
        "token",
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.RR_OAUTH_REDIRECT_URI,
            "code_verifier": decrypt(verifier_encrypted),
            "resource": settings.RR_BASE_URL,
        },
    )
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")
    if status_code != 200 or not access_token or not refresh_token:
        raise RRIntegrationError(
            "token_exchange_failed",
            "Reactive Resume did not issue an authorization. Please try again.",
            status=502,
        )

    userinfo = _userinfo(access_token)
    rr_user_id = userinfo.get("sub")
    if not rr_user_id:
        revoke_refresh_token(refresh_token)
        raise RRIntegrationError(
            "missing_subject", "Reactive Resume did not identify the account.", status=502
        )

    previous_refresh = ""
    taken = False
    try:
        with transaction.atomic():
            link = ResumeAccountLink.objects.select_for_update().get(pk=link.pk)
            taken = (
                ResumeAccountLink.objects.filter(rr_user_id=rr_user_id)
                .exclude(pk=link.pk)
                .exists()
            )
            if not taken:
                if link.rr_user_id != rr_user_id:
                    previous_refresh = link.refresh_token_encrypted
                link.rr_user_id = rr_user_id
                link.rr_email = userinfo.get("email") or ""
                link.rr_name = userinfo.get("name") or ""
                link.refresh_token_encrypted = encrypt(refresh_token)
                link.scopes = body.get("scope") or SCOPES
                link.status = ResumeAccountLink.STATUS_CONNECTED
                link.linked_at = timezone.now()
                link.revoked_at = None
                link.last_error = ""
                link.save()
    except IntegrityError:
        # Another job seeker linked the same RR account between our check and save.
        taken = True

    if taken:
        # Nobody may keep this grant: we refuse to store it, so retire it at RR too.
        revoke_refresh_token(refresh_token)
        raise RRIntegrationError(
            "rr_account_already_linked",
            "That Reactive Resume account is already linked to another GradBridge user.",
            status=409,
        )

    if previous_refresh:
        # Re-linked to a different RR account: retire the old authorization.
        revoke_refresh_token(decrypt(previous_refresh))
    return link


def _userinfo(access_token):
    try:
        response = requests.get(
            _endpoint("userinfo"),
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RRIntegrationError(
            "rr_unreachable", "Reactive Resume could not be reached.", status=502
        ) from exc
    if response.status_code != 200:
        raise RRIntegrationError(
            "userinfo_failed", "Reactive Resume did not return the account.", status=502
        )
    return response.json()


def revoke_refresh_token(refresh_token):
    """Best effort: a failure here must not block disconnecting locally."""
    try:
        _post_form(
            "revoke", {"token": refresh_token, "token_type_hint": "refresh_token"}
        )
    except RRIntegrationError:
        pass


def disconnect(user):
    link = ResumeAccountLink.objects.filter(user=user).first()
    if not link:
        return None

    refresh_encrypted = link.refresh_token_encrypted
    link.rr_user_id = None
    link.rr_email = ""
    link.rr_name = ""
    link.refresh_token_encrypted = ""
    link.scopes = ""
    _clear_pending(link)
    link.status = ResumeAccountLink.STATUS_REVOKED
    link.revoked_at = timezone.now()
    link.last_error = ""
    link.save()

    if refresh_encrypted:
        try:
            revoke_refresh_token(decrypt(refresh_encrypted))
        except RRIntegrationError:
            pass  # unreadable token: nothing left to revoke from our side
    return link


def _refresh(refresh_token):
    """POST the refresh grant, retrying lost responses with the SAME token.

    RR may rotate the token and then fail to deliver the response (a timeout
    while it is busy, a dropped connection). Presenting a rotated token
    normally revokes the grant, but RR replays the original response for a
    retry inside its reuse window (60 s), so the retry gets the new token.
    Only transport failures and 5xx responses are retried.
    """
    last_error = RRIntegrationError(
        "token_refresh_failed", "Reactive Resume did not renew the authorization.", status=502
    )
    for delay in (0, *REFRESH_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            status_code, body = _post_form(
                "token",
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "resource": settings.RR_BASE_URL,
                },
            )
        except RRIntegrationError as exc:
            last_error = exc
            continue
        if status_code >= 500:
            continue
        return status_code, body
    raise last_error


def get_access_token(user):
    """Mint a short-lived RR access token for `user`; never stored.

    The refresh token rotates on every use, so this holds a row lock while it
    refreshes (including retries, see _refresh) and saves the new one before
    the lock is released. Two callers must never present the same refresh
    token concurrently, or RR revokes the family.
    """
    # Errors are raised only after the block commits, so a "needs reconnecting"
    # status written inside it is not rolled back with the exception.
    failure = None
    with transaction.atomic():
        link = (
            ResumeAccountLink.objects.select_for_update()
            .filter(user=user, status=ResumeAccountLink.STATUS_CONNECTED)
            .first()
        )
        if not link or not link.refresh_token_encrypted:
            failure = RRIntegrationError(
                "not_connected", "Your Reactive Resume account is not connected.", status=409
            )
        else:
            try:
                refresh_token = decrypt(link.refresh_token_encrypted)
            except RRIntegrationError as exc:
                # Encrypted with another RR_TOKEN_ENCRYPTION_KEY (the key was
                # rotated or lost, e.g. a restore without it). It can never be
                # read again, so ask the job seeker to reconnect.
                link.status = ResumeAccountLink.STATUS_ERROR
                link.refresh_token_encrypted = ""
                link.last_error = "The stored authorization can no longer be read."
                link.save()
                failure = exc
                refresh_token = None
            if refresh_token is not None:
                try:
                    status_code, body = _refresh(refresh_token)
                except RRIntegrationError as exc:
                    # RR could not be reached even after retries. The stored token
                    # may still be valid (or replayable), so the link is left as is.
                    failure = exc
                    status_code, body = None, {}
        if failure is None:
            access_token = body.get("access_token")
            new_refresh = body.get("refresh_token")

            if status_code == 200 and access_token:
                if new_refresh:
                    link.refresh_token_encrypted = encrypt(new_refresh)
                    link.save(update_fields=["refresh_token_encrypted", "updated_at"])
            elif body.get("error") == "invalid_grant":
                link.status = ResumeAccountLink.STATUS_ERROR
                link.refresh_token_encrypted = ""
                link.last_error = "Reactive Resume no longer accepts this authorization."
                link.save()
                failure = RRIntegrationError(
                    "reconnect_required",
                    "Your Reactive Resume authorization has expired or was revoked. Please reconnect.",
                    status=409,
                )
            else:
                failure = RRIntegrationError(
                    "token_refresh_failed",
                    "Reactive Resume did not renew the authorization.",
                    status=502,
                )

    if failure:
        raise failure
    return access_token


def _token_subject(access_token):
    """`sub` of an access token RR has just issued to us, or None if not a JWT.

    The token comes straight from RR's token endpoint over our authenticated
    back-channel, so its claims are read without checking the signature, the
    same trust we place in the rest of that response. Unlike userinfo, this
    does not depend on the RR browser session in which the job seeker approved
    access: RR ends that session after some days and userinfo then rejects
    tokens bound to it, while refreshing and the API keep working.
    """
    parts = access_token.split(".")
    if len(parts) != 3:
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except ValueError:
        return None
    sub = claims.get("sub") if isinstance(claims, dict) else None
    return sub if isinstance(sub, str) else None


def check_connection(user):
    """Prove the stored authorization still works: refresh, then read the account."""
    access_token = get_access_token(user)
    subject = _token_subject(access_token) or _userinfo(access_token).get("sub")
    link = ResumeAccountLink.objects.get(user=user)
    if subject != link.rr_user_id:
        raise RRIntegrationError(
            "subject_mismatch",
            "Reactive Resume returned a different account than the one linked.",
            status=409,
        )
    try:
        response = requests.get(
            f"{settings.RR_INTERNAL_URL}/api/openapi/resumes",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RRIntegrationError(
            "rr_unreachable", "Reactive Resume could not be reached.", status=502
        ) from exc
    if response.status_code != 200:
        raise RRIntegrationError(
            "rr_api_failed", "Reactive Resume rejected the request.", status=502
        )
    resumes = response.json()
    return {"rr_user_id": link.rr_user_id, "resume_count": len(resumes)}
