"""
Settings for GradBridge deployments (containers, Azure Container Apps).

settings_server.py is specific to peeljobs.com (its hosts, cookie domain,
SES mail, HSTS). This module keeps the shared base and reads everything that
differs per environment from environment variables, so one image runs in a
local production drill and in Azure.

Required: SECRET_KEY, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT,
ALLOWED_HOSTS. See docs/gradbridge-deployment.md for the full list.
"""

import os

from .settings import *
from .settings import env_bool


def env_list(name, default=""):
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


DEBUG = env_bool("DEBUG", False)
TEMPLATE_DEBUG = DEBUG

SECRET_KEY = os.environ["SECRET_KEY"]  # fail fast rather than run without one

# USE_TZ is False, so datetimes are stored as naive local time in this zone.
# Choose it before the first data is written; changing it later shifts every
# stored time. GradBridge serves Australia and Singapore, so the fallback is
# Sydney rather than the upstream Asia/Kolkata.
TIME_ZONE = os.getenv("TIME_ZONE") or "Australia/Sydney"

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOWED_ORIGIN_REGEXES = []

# TLS ends at the ingress (Azure Container Apps, or a reverse proxy), which
# forwards the original scheme. The ingress also enforces HTTPS, so Django
# does not redirect by default: internal service-to-service calls are plain
# HTTP and must not be bounced to https.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_CONTENT_TYPE_NOSNIFF = True

# Mail: console by default (no SES dependency); set EMAIL_BACKEND to an SMTP
# or SES backend in a real deployment.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)

# Without a Celery worker, run tasks (e.g. verification mail) inline.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", True)
CELERY_TASK_EAGER_PROPAGATES = False

# The published-resume store must be a persistent volume in production.
GRADBRIDGE_PRIVATE_MEDIA_ROOT = os.getenv(
    "GRADBRIDGE_PRIVATE_MEDIA_ROOT", "/data/private_media"
)
MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/data/media")
