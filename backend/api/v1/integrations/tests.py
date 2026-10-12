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

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from peeldb.models import ResumeAccountLink, User

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
        self.resumes = [{"id": "r1"}]

    def post(self, url, data=None, json=None, timeout=None):
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
            if self.refresh_error:
                return FakeResponse(400, {"error": self.refresh_error})
            self.refresh_counter += 1
            return FakeResponse(
                200,
                {
                    "access_token": f"access-r{self.refresh_counter}",
                    "refresh_token": f"refresh-r{self.refresh_counter}",
                },
            )
        if name == "revoke":
            return FakeResponse(200, {})
        raise AssertionError(f"unexpected POST {url}")

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
class RRLinkTests(TestCase):
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

    def _linked(self):
        _url, query = self.connect()
        self.assertEqual(self.callback(state=query["state"]).status_code, 200)

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
