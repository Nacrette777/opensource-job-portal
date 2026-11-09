"""Rate limits on the anonymous auth and contact endpoints (api/v1/throttles.py)."""

from django.conf import settings
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

RATES = {
    "login_email": "2/hour",
    "password_reset_email": "2/hour",
    "verification_email": "2/hour",
    "register_global": "2/hour",
    "contact_global": "2/hour",
}
THROTTLED = override_settings(
    REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": RATES}
)


class ThrottleTestCase(TestCase):
    def setUp(self):
        caches["default"].clear()
        self.client = APIClient()

    def post(self, name, data=None):
        return self.client.post(reverse(name), data or {}, format="json")


@THROTTLED
class EmailThrottleTests(ThrottleTestCase):
    def test_login_is_limited_per_target_email(self):
        url = "api:v1:auth:login"
        for _ in range(2):
            response = self.post(url, {"email": "a@example.test", "password": "wrong"})
            self.assertEqual(response.status_code, 400)
        # Case and surrounding spaces do not make it a different address.
        response = self.post(url, {"email": " A@Example.test ", "password": "wrong"})
        self.assertEqual(response.status_code, 429)
        self.assertRegex(
            response.json()["detail"],
            r"^Too many attempts\. Please try again in \d+ minutes?\.$",
        )
        # Another account is unaffected.
        response = self.post(url, {"email": "b@example.test", "password": "wrong"})
        self.assertEqual(response.status_code, 400)

    def test_job_seeker_and_recruiter_login_share_the_count(self):
        data = {"email": "a@example.test", "password": "wrong"}
        self.post("api:v1:auth:login", data)
        self.post("api:v1:recruiter:login", data)
        self.assertEqual(self.post("api:v1:auth:login", data).status_code, 429)

    def test_password_reset_and_verification_mail_are_limited(self):
        for name in (
            "api:v1:auth:forgot-password",
            "api:v1:recruiter:forgot-password",
            "api:v1:auth:resend-verification",
            "api:v1:recruiter:resend-verification",
        ):
            with self.subTest(name=name):
                caches["default"].clear()
                for _ in range(2):
                    self.assertNotEqual(
                        self.post(name, {"email": "a@example.test"}).status_code, 429
                    )
                self.assertEqual(
                    self.post(name, {"email": "a@example.test"}).status_code, 429
                )

    def test_requests_without_an_email_are_not_counted(self):
        for _ in range(4):
            response = self.post("api:v1:auth:forgot-password", {})
            self.assertEqual(response.status_code, 400)


@THROTTLED
class GlobalThrottleTests(ThrottleTestCase):
    def test_registration_and_contact_have_a_site_wide_ceiling(self):
        for name in (
            "api:v1:auth:register",
            "api:v1:recruiter:register",
            "api:v1:contact:submit",
        ):
            with self.subTest(name=name):
                caches["default"].clear()
                # Invalid requests count too: the limit runs before validation.
                for _ in range(2):
                    self.assertEqual(self.post(name).status_code, 400)
                self.assertEqual(self.post(name).status_code, 429)

    def test_both_registration_forms_share_the_ceiling(self):
        self.post("api:v1:auth:register")
        self.post("api:v1:recruiter:register")
        self.assertEqual(self.post("api:v1:auth:register").status_code, 429)


class UnconfiguredThrottleTests(ThrottleTestCase):
    def test_no_rates_means_no_limit(self):
        for _ in range(10):
            response = self.post(
                "api:v1:auth:login", {"email": "a@example.test", "password": "wrong"}
            )
            self.assertEqual(response.status_code, 400)


@THROTTLED
@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "throttle": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "test_throttle_cache",
        },
    },
    GRADBRIDGE_THROTTLE_CACHE="throttle",
)
class DatabaseCacheThrottleTests(ThrottleTestCase):
    """The deployment setup: counts in a shared database table."""

    def setUp(self):
        call_command("createcachetable", verbosity=0)
        super().setUp()

    def test_counts_are_shared_and_emails_are_not_stored(self):
        data = {"email": "a@example.test", "password": "wrong"}
        for _ in range(2):
            self.post("api:v1:auth:login", data)
        self.assertEqual(self.post("api:v1:auth:login", data).status_code, 429)
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key FROM test_throttle_cache")
            keys = [row[0] for row in cursor.fetchall()]
        self.assertEqual(len(keys), 1)
        self.assertIn("login_email", keys[0])
        self.assertNotIn("example", keys[0])
