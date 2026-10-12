"""
GradBridge: link a job seeker's Reactive Resume (RR) account.

The SvelteKit site drives the browser side: `connect/` returns RR's authorize
URL to redirect to, and RR sends the browser back to a site route that posts
the code and state here as `callback/`. All OAuth secrets stay in this server.
"""

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from peeldb.models import ResumeAccountLink

from . import rr_client
from .serializers import (
    RRCallbackSerializer,
    RRCheckResponseSerializer,
    RRConnectResponseSerializer,
    RRErrorSerializer,
    RRLinkStatusSerializer,
)

TAGS = ["Integrations"]


def _guard(request):
    """Job seekers only, and only when the integration is configured."""
    if request.user.user_type != "JS":
        return Response(
            {"code": "forbidden", "error": "Only job seekers can link Reactive Resume."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not rr_client.is_configured():
        return Response(
            {
                "code": "not_configured",
                "error": "The Reactive Resume integration is not configured on this server.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return None


def _error(exc):
    return Response({"code": exc.code, "error": exc.message}, status=exc.status)


def _status_payload(user):
    link = ResumeAccountLink.objects.filter(user=user).first()
    return RRLinkStatusSerializer.build(
        link, configured=rr_client.is_configured(), rr_base_url=settings.RR_BASE_URL
    )


@extend_schema(
    tags=TAGS,
    summary="Reactive Resume link status",
    responses={200: RRLinkStatusSerializer, 403: RRErrorSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rr_status(request):
    if request.user.user_type != "JS":
        return Response(
            {"code": "forbidden", "error": "Only job seekers can link Reactive Resume."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return Response(_status_payload(request.user))


@extend_schema(
    tags=TAGS,
    summary="Start linking Reactive Resume",
    description="Returns RR's authorization URL (PKCE, single-use state, 10 minutes).",
    request=None,
    responses={200: RRConnectResponseSerializer, 403: RRErrorSerializer, 503: RRErrorSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rr_connect(request):
    if denied := _guard(request):
        return denied
    return Response({"authorization_url": rr_client.start_authorization(request.user)})


@extend_schema(
    tags=TAGS,
    summary="Finish linking Reactive Resume",
    description=(
        "Receives the code, state and iss RR redirected back with. The account "
        "linked is the one RR names in `sub`; an RR account already linked to "
        "another user is refused (409)."
    ),
    request=RRCallbackSerializer,
    responses={200: RRLinkStatusSerializer, 400: RRErrorSerializer, 409: RRErrorSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rr_callback(request):
    if denied := _guard(request):
        return denied
    serializer = RRCallbackSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"code": "invalid_request", "error": "Missing authorization parameters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        rr_client.complete_authorization(request.user, **serializer.validated_data)
    except rr_client.RRIntegrationError as exc:
        return _error(exc)
    return Response(_status_payload(request.user))


@extend_schema(
    tags=TAGS,
    summary="Disconnect Reactive Resume",
    description=(
        "Revokes the stored refresh token at RR and forgets the link. RR access "
        "tokens cannot be revoked early, but none are ever stored here."
    ),
    request=None,
    responses={200: RRLinkStatusSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rr_disconnect(request):
    if denied := _guard(request):
        return denied
    rr_client.disconnect(request.user)
    return Response(_status_payload(request.user))


@extend_schema(
    tags=TAGS,
    summary="Check the Reactive Resume link",
    description="Renews the authorization and reads the linked RR account.",
    request=None,
    responses={200: RRCheckResponseSerializer, 409: RRErrorSerializer, 502: RRErrorSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rr_check(request):
    if denied := _guard(request):
        return denied
    try:
        result = rr_client.check_connection(request.user)
    except rr_client.RRIntegrationError as exc:
        return _error(exc)
    return Response({"ok": True, "resume_count": result["resume_count"]})
