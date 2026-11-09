"""Server-time helpers for the GradBridge integration (USE_TZ is off)."""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def as_server_time(value):
    """Attach TIME_ZONE to a naive datetime (USE_TZ is off, so that is what it is).

    Sent naive, a browser reads the time as its own local time, while RR's timestamps
    carry UTC; the publish page then showed "published 20:12 · saved 17:10" for edits
    two minutes apart. With the offset both convert to the viewer's time.
    """
    if value is None or timezone.is_aware(value):
        return value
    return timezone.make_aware(value, ZoneInfo(settings.TIME_ZONE))
