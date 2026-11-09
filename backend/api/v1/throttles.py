"""
Rate limits for the anonymous auth and contact endpoints.

The browser does not call these endpoints itself: the SvelteKit servers (site
and recruiter) do, so every request reaches the API from the same few
addresses and a per-IP limit would throttle all users together. The limits
are therefore keyed on what the request is about instead:

- login, password reset and verification mail: the target email address, so
  one account cannot be guessed at or flooded with mail;
- registration and the contact form: one site-wide counter, a ceiling on how
  many accounts or messages can be created per hour.

A scope is off unless REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] names it, so
development and the test suite run unthrottled; settings_gradbridge sets the
rates for deployments. Counts are kept in the cache named by
GRADBRIDGE_THROTTLE_CACHE (default "default"); a deployment points it at a
database cache so that every gunicorn worker shares one count.
"""

import hashlib
import math

from django.conf import settings
from django.core.cache import caches
from rest_framework import exceptions
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """DRF's handler, with a throttle message people can act on.

    The default says "Request was throttled. Expected available in 3542
    seconds."; the auth pages show `detail` as it is.
    """
    if isinstance(exc, exceptions.Throttled):
        if exc.wait:
            minutes = math.ceil(exc.wait / 60)
            when = f"in {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            when = "later"
        exc.detail = f"Too many attempts. Please try again {when}."
    return drf_exception_handler(exc, context)


class ConfiguredRateThrottle(SimpleRateThrottle):
    """A SimpleRateThrottle that is a no-op when its scope has no rate."""

    def __init__(self):
        self.cache = caches[getattr(settings, "GRADBRIDGE_THROTTLE_CACHE", "default")]
        super().__init__()

    def get_rate(self):
        # Read at request time (the class attribute THROTTLE_RATES is bound at
        # import), and None rather than ImproperlyConfigured for a missing scope.
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)


class EmailRateThrottle(ConfiguredRateThrottle):
    """Counts requests per target email (normalised, stored only as a hash)."""

    def get_cache_key(self, request, view):
        data = request.data if hasattr(request.data, "get") else {}
        email = data.get("email")
        if not isinstance(email, str) or not email.strip():
            return None  # nothing to count against; the serializer rejects it
        ident = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class GlobalRateThrottle(ConfiguredRateThrottle):
    """One counter for every caller of the endpoint."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": "all"}


class LoginEmailThrottle(EmailRateThrottle):
    scope = "login_email"


class PasswordResetEmailThrottle(EmailRateThrottle):
    scope = "password_reset_email"


class VerificationEmailThrottle(EmailRateThrottle):
    scope = "verification_email"


class RegisterGlobalThrottle(GlobalRateThrottle):
    scope = "register_global"


class ContactGlobalThrottle(GlobalRateThrottle):
    scope = "contact_global"
