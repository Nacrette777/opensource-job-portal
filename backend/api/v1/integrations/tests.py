"""
Tests for the GradBridge Reactive Resume (RR) account link.

RR is never contacted: `requests.post` / `requests.get` inside rr_client are
replaced by a fake RR that records what it was sent.
"""

import base64
import hashlib
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from peeldb.models import ResumeAccountLink, ResumeIntegrationRequest, User

from . import rr_client

RR = "http://rr.test"
REDIRECT = "http://site.test/profile/integrations/rr/callback/"
RR_SETTINGS = {
    "RR_BASE_URL": RR,
    "RR_INTERNAL_URL": RR,
    "RR_OAUTH_CLIENT_ID": "client-123",
    "RR_OAUTH_CLIENT_SECRET": "secret-xyz",
    "RR_OAUTH_REDIRECT_URI": REDIRECT,
    "RR_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
}


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.content = b"x"

    def json(self):
        return self._body


class FakeRR:
    """Minimal stand-in for RR's OAuth + API endpoints."""

    def __init__(self, sub="rr-user-1"):
        self.sub = sub
        self.posts = []
        self.gets = []
        self.refresh_counter = 0
        self.refresh_error = None
        self.refresh_down = False
        self.refresh_lost_responses = 0
        self.refresh_replays = {}
        self.resumes = [{"id": "r1"}]
        self.imports = []
        self.drafts = {}
        self.import_failure = None
        self.before_import = None

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        if url.endswith("/api/openapi/resumes/import/json-resume"):
            return self._import(json, headers)
        name = url.rsplit("/", 1)[-1]
        self.posts.append((name, dict(data or {})))
        if name == "token" and data["grant_type"] == "authorization_code":
            return FakeResponse(
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "scope": rr_client.SCOPES,
                    "token_type": "Bearer",
                },
            )
        if name == "token" and data["grant_type"] == "refresh_token":
            if self.refresh_down:
                raise requests.ConnectionError("RR unreachable")
            if self.refresh_error:
                return FakeResponse(400, {"error": self.refresh_error})
            presented = data["refresh_token"]
            if presented in self.refresh_replays:
                # RR's reuse window: the same response for a retried token.
                return FakeResponse(200, self.refresh_replays[presented])
            self.refresh_counter += 1
            response = {
                "access_token": f"access-r{self.refresh_counter}",
                "refresh_token": f"refresh-r{self.refresh_counter}",
            }
            self.refresh_replays[presented] = response
            if self.refresh_lost_responses:
                # Rotated on RR, but the response never reaches the client.
                self.refresh_lost_responses -= 1
                raise requests.ReadTimeout("response lost")
            return FakeResponse(200, response)
        if name == "revoke":
            return FakeResponse(200, {})
        raise AssertionError(f"unexpected POST {url}")

    def _import(self, body, headers):
        self.imports.append({"body": body, "headers": headers})
        if self.before_import:
            self.before_import()
        if self.import_failure == "network":
            raise requests.ConnectionError("down")
        if self.import_failure and self.import_failure != "lost":
            return FakeResponse(*self.import_failure)
        request_id = body["requestId"]
        created = request_id not in self.drafts
        self.drafts.setdefault(request_id, f"draft-{len(self.drafts) + 1}")
        if self.import_failure == "lost":
            # RR committed the draft, but the response never reaches us.
            raise requests.ReadTimeout("response lost")
        return FakeResponse(200, {"id": self.drafts[request_id], "created": created})

    def get(self, url, headers=None, timeout=None):
        self.gets.append((url, headers))
        if url.endswith("/userinfo"):
            return FakeResponse(
                200, {"sub": self.sub, "email": "student@example.test", "name": "Student"}
            )
        if url.endswith("/api/openapi/resumes"):
            return FakeResponse(200, self.resumes)
        raise AssertionError(f"unexpected GET {url}")

    def calls(self, name):
        return [data for n, data in self.posts if n == name]


def make_user(email, user_type="JS"):
    user = User.objects.create_user(username=email, email=email, password="Str0ng!Passw0rd")
    user.user_type = user_type
    user.is_active = True
    user.save()
    return user


@override_settings(**RR_SETTINGS)
class RRTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("seeker@example.test")
        self.client.force_authenticate(user=self.user)
        self.rr = FakeRR()
        patcher_post = mock.patch.object(rr_client.requests, "post", side_effect=self.rr.post)
        patcher_get = mock.patch.object(rr_client.requests, "get", side_effect=self.rr.get)
        patcher_post.start()
        patcher_get.start()
        self.addCleanup(patcher_post.stop)
        self.addCleanup(patcher_get.stop)
        patcher_sleep = mock.patch.object(rr_client.time, "sleep")
        self.sleep = patcher_sleep.start()
        self.addCleanup(patcher_sleep.stop)

    # --- helpers -------------------------------------------------------------

    def connect(self):
        response = self.client.post(reverse("api:v1:integrations:rr-connect"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        url = urlparse(response.data["authorization_url"])
        return url, {k: v[0] for k, v in parse_qs(url.query).items()}

    def callback(self, **overrides):
        payload = {"code": "code-1", "iss": f"{RR}/api/auth", **overrides}
        return self.client.post(
            reverse("api:v1:integrations:rr-callback"), payload, format="json"
        )

    def link(self):
        return ResumeAccountLink.objects.get(user=self.user)

    def _linked(self):
        _url, query = self.connect()
        self.assertEqual(self.callback(state=query["state"]).status_code, 200)


class RRLinkTests(RRTestBase):
    # --- access --------------------------------------------------------------

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("api:v1:integrations:rr-status"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_recruiters_are_refused(self):
        self.client.force_authenticate(user=make_user("hr@example.test", user_type="RR"))
        response = self.client.post(reverse("api:v1:integrations:rr-connect"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(RR_OAUTH_CLIENT_SECRET="")
    def test_unconfigured_server_reports_it(self):
        response = self.client.post(reverse("api:v1:integrations:rr-connect"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        status_response = self.client.get(reverse("api:v1:integrations:rr-status"))
        self.assertFalse(status_response.data["configured"])

    # --- connect -------------------------------------------------------------

    def test_connect_builds_a_pkce_authorization_request(self):
        url, query = self.connect()

        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", f"{RR}/api/auth/oauth2/authorize")
        self.assertEqual(query["client_id"], "client-123")
        self.assertEqual(query["redirect_uri"], REDIRECT)
        self.assertEqual(query["code_challenge_method"], "S256")
        self.assertEqual(query["resource"], RR)
        self.assertIn("offline_access", query["scope"])

        link = self.link()
        self.assertEqual(link.oauth_state, query["state"])
        verifier = rr_client.decrypt(link.oauth_code_verifier_encrypted)
        self.assertNotIn(verifier, link.oauth_code_verifier_encrypted)
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], expected)
        status_response = self.client.get(reverse("api:v1:integrations:rr-status"))
        self.assertEqual(status_response.data["status"], "not_connected")

    # --- callback ------------------------------------------------------------

    def test_callback_links_the_account_rr_names(self):
        _url, query = self.connect()
        verifier = rr_client.decrypt(self.link().oauth_code_verifier_encrypted)

        response = self.callback(state=query["state"])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], "connected")
        self.assertEqual(response.data["rr_email"], "student@example.test")
        link = self.link()
        self.assertEqual(link.rr_user_id, "rr-user-1")
        self.assertNotIn("refresh-1", link.refresh_token_encrypted)
        self.assertEqual(rr_client.decrypt(link.refresh_token_encrypted), "refresh-1")
        self.assertEqual(link.oauth_state, "")
        self.assertEqual(link.oauth_code_verifier_encrypted, "")

        exchange = self.rr.calls("token")[0]
        self.assertEqual(exchange["code_verifier"], verifier)
        self.assertEqual(exchange["resource"], RR)
        self.assertEqual(exchange["redirect_uri"], REDIRECT)
        self.assertEqual(exchange["client_secret"], "secret-xyz")

    def test_callback_rejects_an_unknown_state(self):
        self.connect()
        response = self.callback(state="forged")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_state")
        self.assertEqual(self.rr.calls("token"), [])

    def test_state_is_single_use(self):
        _url, query = self.connect()
        self.assertEqual(self.callback(state=query["state"]).status_code, 200)

        replay = self.callback(state=query["state"])

        self.assertEqual(replay.data["code"], "invalid_state")
        self.assertEqual(len(self.rr.calls("token")), 1)

    def test_state_from_another_user_is_rejected(self):
        _url, query = self.connect()
        self.client.force_authenticate(user=make_user("other@example.test"))
        response = self.callback(state=query["state"])
        self.assertEqual(response.data["code"], "invalid_state")
        self.assertEqual(self.rr.calls("token"), [])

    def test_expired_authorization_is_rejected(self):
        _url, query = self.connect()
        ResumeAccountLink.objects.filter(user=self.user).update(
            oauth_started_at=timezone.now() - timedelta(minutes=11)
        )
        response = self.callback(state=query["state"])
        self.assertEqual(response.data["code"], "authorization_expired")
        self.assertEqual(self.rr.calls("token"), [])

    def test_unexpected_issuer_is_rejected(self):
        _url, query = self.connect()
        response = self.callback(state=query["state"], iss="http://evil.test/api/auth")
        self.assertEqual(response.data["code"], "invalid_issuer")
        self.assertEqual(self.rr.calls("token"), [])

    def test_denied_consent_links_nothing(self):
        _url, query = self.connect()
        response = self.callback(state=query["state"], code="", error="access_denied")
        self.assertEqual(response.data["code"], "authorization_denied")
        self.assertIsNone(self.link().rr_user_id)

    def test_rr_account_linked_to_someone_else_is_refused_and_revoked(self):
        other = make_user("other@example.test")
        ResumeAccountLink.objects.create(
            user=other, rr_user_id="rr-user-1", status=ResumeAccountLink.STATUS_CONNECTED
        )
        _url, query = self.connect()

        response = self.callback(state=query["state"])

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "rr_account_already_linked")
        self.assertIsNone(self.link().rr_user_id)
        self.assertEqual(self.link().refresh_token_encrypted, "")
        self.assertEqual(self.rr.calls("revoke")[0]["token"], "refresh-1")

    # --- disconnect ----------------------------------------------------------

    def test_disconnect_revokes_at_rr_and_forgets_the_link(self):
        self._linked()

        response = self.client.post(reverse("api:v1:integrations:rr-disconnect"))

        self.assertEqual(response.data["status"], "not_connected")
        revoke = self.rr.calls("revoke")[0]
        self.assertEqual(revoke["token"], "refresh-1")
        self.assertEqual(revoke["token_type_hint"], "refresh_token")
        link = self.link()
        self.assertIsNone(link.rr_user_id)
        self.assertEqual(link.refresh_token_encrypted, "")
        self.assertEqual(link.status, ResumeAccountLink.STATUS_REVOKED)

    def test_disconnected_rr_account_can_be_linked_by_someone_else(self):
        self._linked()
        self.client.post(reverse("api:v1:integrations:rr-disconnect"))

        self.client.force_authenticate(user=make_user("other@example.test"))
        _url, query = self.connect()
        response = self.callback(state=query["state"])

        self.assertEqual(response.status_code, 200, response.data)

    # --- refresh -------------------------------------------------------------

    def test_access_tokens_are_minted_per_use_and_the_refresh_token_rotates(self):
        self._linked()

        first = rr_client.get_access_token(self.user)
        second = rr_client.get_access_token(self.user)

        self.assertEqual((first, second), ("access-r1", "access-r2"))
        presented = [c["refresh_token"] for c in self.rr.calls("token") if c["grant_type"] == "refresh_token"]
        self.assertEqual(presented, ["refresh-1", "refresh-r1"])
        self.assertEqual(rr_client.decrypt(self.link().refresh_token_encrypted), "refresh-r2")

    def test_a_lost_refresh_response_is_recovered_with_the_same_token(self):
        self._linked()
        self.rr.refresh_lost_responses = 1

        access = rr_client.get_access_token(self.user)

        self.assertEqual(access, "access-r1")
        presented = [c["refresh_token"] for c in self.rr.calls("token") if c["grant_type"] == "refresh_token"]
        self.assertEqual(presented, ["refresh-1", "refresh-1"])  # retried with the same token
        link = self.link()
        self.assertEqual(link.status, ResumeAccountLink.STATUS_CONNECTED)
        self.assertEqual(rr_client.decrypt(link.refresh_token_encrypted), "refresh-r1")
        # The next refresh uses the rotated token and keeps working.
        self.assertEqual(rr_client.get_access_token(self.user), "access-r2")

    def test_rr_down_does_not_drop_the_link(self):
        self._linked()
        self.rr.refresh_down = True

        with self.assertRaises(rr_client.RRIntegrationError) as caught:
            rr_client.get_access_token(self.user)

        self.assertEqual(caught.exception.code, "rr_unreachable")
        self.assertEqual(len(self.sleep.call_args_list), len(rr_client.REFRESH_RETRY_DELAYS))
        link = self.link()
        self.assertEqual(link.status, ResumeAccountLink.STATUS_CONNECTED)
        self.assertEqual(rr_client.decrypt(link.refresh_token_encrypted), "refresh-1")

    def test_rejected_refresh_token_is_persisted_as_needs_reconnect(self):
        self._linked()
        self.rr.refresh_error = "invalid_grant"

        with self.assertRaises(rr_client.RRIntegrationError) as caught:
            rr_client.get_access_token(self.user)

        self.assertEqual(caught.exception.code, "reconnect_required")
        link = self.link()  # re-read: the status must have been committed
        self.assertEqual(link.status, ResumeAccountLink.STATUS_ERROR)
        self.assertEqual(link.refresh_token_encrypted, "")
        status_response = self.client.get(reverse("api:v1:integrations:rr-status"))
        self.assertEqual(status_response.data["status"], "needs_reconnect")

    def test_check_renews_and_reads_the_linked_account(self):
        self._linked()

        response = self.client.post(reverse("api:v1:integrations:rr-check"))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"ok": True, "resume_count": 1})
        self.assertEqual(self.rr.gets[-1][1]["Authorization"], "Bearer access-r1")

    def test_check_without_a_link_is_a_conflict(self):
        response = self.client.post(reverse("api:v1:integrations:rr-check"))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "not_connected")


class RRDraftTests(RRTestBase):
    request_id = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"

    def setUp(self):
        super().setUp()
        self.user.first_name = "Test"
        self.user.last_name = "Student"
        self.user.job_role = "Data Analyst"
        self.user.save()

    def create(self, request_id=None):
        return self.client.post(
            reverse("api:v1:integrations:rr-create-draft"),
            {"request_id": request_id or self.request_id},
            format="json",
        )

    def test_creates_a_draft_from_the_profile_in_the_linked_account(self):
        self._linked()

        response = self.create()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "succeeded")
        self.assertEqual(response.data["external_resume_id"], "draft-1")
        self.assertEqual(response.data["editor_url"], f"{RR}/builder/draft-1")
        sent = self.rr.imports[0]
        self.assertEqual(sent["body"]["requestId"], self.request_id)
        self.assertEqual(sent["body"]["resume"]["basics"]["name"], "Test Student")
        self.assertEqual(sent["body"]["resume"]["basics"]["label"], "Data Analyst")
        self.assertTrue(sent["headers"]["Authorization"].startswith("Bearer access-r"))

        req = ResumeIntegrationRequest.objects.get(id=self.request_id)
        self.assertEqual(req.user, self.user)
        self.assertEqual(req.rr_user_id, "rr-user-1")
        self.assertEqual(len(req.source_sha256), 64)
        self.assertEqual(req.attempts, 1)

    def test_resubmitting_the_same_request_returns_the_same_draft(self):
        self._linked()

        first = self.create()
        second = self.create()

        self.assertEqual(first.data["external_resume_id"], second.data["external_resume_id"])
        self.assertEqual(ResumeIntegrationRequest.objects.count(), 1)
        # Already succeeded: answered from our record, RR is not called again.
        self.assertEqual(len(self.rr.imports), 1)

    def test_a_new_request_creates_a_new_draft(self):
        self._linked()

        self.create()
        other = self.create("0e9d8c7b-6a5f-4e3d-9c2b-1a0f9e8d7c6b")

        self.assertEqual(other.data["external_resume_id"], "draft-2")

    def test_retry_after_lost_response_reuses_the_request_id(self):
        self._linked()
        self.rr.import_failure = "network"

        failed = self.create()

        self.assertEqual(failed.status_code, 502)
        self.assertEqual(failed.data["code"], "rr_unreachable")
        req = ResumeIntegrationRequest.objects.get(id=self.request_id)
        self.assertEqual(req.status, ResumeIntegrationRequest.STATUS_FAILED)

        self.rr.import_failure = None
        retried = self.create()

        self.assertEqual(retried.data["status"], "succeeded")
        self.assertEqual([i["body"]["requestId"] for i in self.rr.imports], [self.request_id] * 2)
        self.assertEqual(ResumeIntegrationRequest.objects.get(id=self.request_id).attempts, 2)

    def test_rr_rejecting_the_document_is_reported(self):
        self._linked()
        self.rr.import_failure = (
            400,
            {"code": "INVALID_JSON_RESUME", "message": "Problem fields: basics"},
        )

        response = self.create()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_profile")
        self.assertIn("basics", response.data["error"])

    def test_requires_a_linked_account(self):
        response = self.create()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "not_connected")
        self.assertFalse(ResumeIntegrationRequest.objects.exists())
        self.assertEqual(self.rr.imports, [])

    def test_another_users_request_id_is_not_found(self):
        self._linked()
        self.create()
        other = make_user("other@example.test")
        ResumeAccountLink.objects.create(
            user=other,
            rr_user_id="rr-user-2",
            status=ResumeAccountLink.STATUS_CONNECTED,
            refresh_token_encrypted=rr_client.encrypt("refresh-other"),
        )
        self.client.force_authenticate(user=other)

        response = self.create()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.rr.imports), 1)

    def test_request_id_must_be_a_uuid(self):
        self._linked()
        response = self.create("not-a-uuid")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rr.imports, [])

    def test_list_shows_only_the_users_own_drafts(self):
        self._linked()
        self.create()
        other = make_user("other@example.test")
        ResumeIntegrationRequest.objects.create(user=other, external_resume_id="theirs")

        response = self.client.get(reverse("api:v1:integrations:rr-drafts"))

        self.assertEqual([d["external_resume_id"] for d in response.data], ["draft-1"])

    def test_retry_after_rr_created_the_draft_but_the_response_was_lost(self):
        self._linked()
        self.rr.import_failure = "lost"

        failed = self.create()

        self.assertEqual(failed.data["code"], "rr_unreachable")
        self.assertEqual(len(self.rr.drafts), 1)  # RR did create it

        self.rr.import_failure = None
        retried = self.create()

        self.assertEqual(retried.data["status"], "succeeded")
        self.assertEqual(retried.data["external_resume_id"], "draft-1")
        self.assertEqual(len(self.rr.drafts), 1)

    def test_retry_sends_the_document_frozen_on_the_first_attempt(self):
        self._linked()
        self.rr.import_failure = "network"
        self.create()
        first = ResumeIntegrationRequest.objects.get(id=self.request_id)

        self.user.job_role = "Changed After Failure"
        self.user.save()
        self.rr.import_failure = None
        self.create()

        sent = [i["body"]["resume"]["basics"]["label"] for i in self.rr.imports]
        self.assertEqual(sent, ["Data Analyst", "Data Analyst"])
        self.assertEqual(
            ResumeIntegrationRequest.objects.get(id=self.request_id).source_sha256,
            first.source_sha256,
        )

    def test_a_late_failure_does_not_overwrite_a_success(self):
        """Attempt 1 is still waiting on RR when attempt 2 succeeds; then 1 times out."""
        self._linked()

        def concurrent_attempt_succeeds():
            ResumeIntegrationRequest.objects.filter(id=self.request_id).update(
                status=ResumeIntegrationRequest.STATUS_SUCCEEDED,
                external_resume_id="draft-from-attempt-2",
            )

        self.rr.before_import = concurrent_attempt_succeeds
        self.rr.import_failure = "network"

        response = self.create()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "succeeded")
        self.assertEqual(response.data["external_resume_id"], "draft-from-attempt-2")
        req = ResumeIntegrationRequest.objects.get(id=self.request_id)
        self.assertEqual(req.status, ResumeIntegrationRequest.STATUS_SUCCEEDED)
        self.assertEqual(req.error_code, "")

    def test_retry_after_switching_rr_account_is_refused(self):
        """A request started for one RR account must not be retried in another."""
        self._linked()
        self.rr.import_failure = "lost"  # account 1 may now hold the draft
        self.create()
        ResumeAccountLink.objects.filter(user=self.user).update(rr_user_id="rr-user-other")
        self.rr.import_failure = None

        response = self.create()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "rr_account_changed")
        self.assertEqual(len(self.rr.imports), 1)
        req = ResumeIntegrationRequest.objects.get(id=self.request_id)
        self.assertEqual(req.rr_user_id, "rr-user-1")

    def test_retry_after_the_draft_was_deleted_in_rr_is_final(self):
        """RR created the draft, the response was lost, then the student deleted it in RR."""
        self._linked()
        self.rr.import_failure = "lost"
        self.create()
        self.rr.import_failure = (
            410,
            {"code": "IMPORT_TARGET_DELETED", "message": "The resume ... has since been deleted."},
        )

        response = self.create()

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "rr_draft_deleted")
        self.assertIn("Create a new draft", response.data["error"])
        req = ResumeIntegrationRequest.objects.get(id=self.request_id)
        self.assertEqual(req.status, ResumeIntegrationRequest.STATUS_FAILED)
        self.assertEqual(req.error_code, "rr_draft_deleted")

        listed = self.client.get(reverse("api:v1:integrations:rr-drafts")).data
        self.assertEqual([d["retryable"] for d in listed], [False])

        # Further retries of this request are refused without calling RR again.
        self.rr.import_failure = None
        again = self.create()
        self.assertEqual(again.status_code, 410)
        self.assertEqual(again.data["code"], "rr_draft_deleted")
        self.assertEqual(len(self.rr.imports), 2)
        self.assertEqual(ResumeIntegrationRequest.objects.get(id=self.request_id).attempts, 2)

        # A new request creates a new draft as usual.
        fresh = self.create("0e9d8c7b-6a5f-4e3d-9c2b-1a0f9e8d7c6b")
        self.assertEqual(fresh.data["status"], "succeeded")

    def test_rr_refusing_a_reused_request_id_is_final(self):
        self._linked()
        self.rr.import_failure = (
            409,
            {"code": "IMPORT_REQUEST_MISMATCH", "message": "different document"},
        )

        response = self.create()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "rr_request_conflict")
        listed = self.client.get(reverse("api:v1:integrations:rr-drafts")).data
        self.assertEqual([d["retryable"] for d in listed], [False])

    def test_failed_and_pending_drafts_are_retryable_succeeded_ones_are_not(self):
        self._linked()
        self.rr.import_failure = "network"
        self.create()
        self.rr.import_failure = None
        self.create("0e9d8c7b-6a5f-4e3d-9c2b-1a0f9e8d7c6b")

        listed = {
            str(d["id"]): d["retryable"]
            for d in self.client.get(reverse("api:v1:integrations:rr-drafts")).data
        }

        self.assertEqual(
            listed,
            {self.request_id: True, "0e9d8c7b-6a5f-4e3d-9c2b-1a0f9e8d7c6b": False},
        )
