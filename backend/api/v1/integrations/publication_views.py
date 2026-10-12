"""
GradBridge: a job seeker publishes one of their Reactive Resume resumes.

Recruiters only ever see the version the publication pointer names; see
publishing.py for how a version is snapshotted and stored.
"""

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from peeldb.models import ResumePublication, ResumeVersion

from . import publishing, rr_client
from .serializers import RRErrorSerializer
from .views import _error, _guard

TAGS = ["Integrations"]
HISTORY_LIMIT = 10


class RRResumeSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    updated_at = serializers.CharField(allow_blank=True)


class ResumeVersionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = ResumeVersion
        fields = [
            "id",
            "title",
            "external_resume_id",
            "rr_updated_at",
            "pdf_size",
            "pdf_sha256",
            "created_at",
            "is_current",
        ]

    def get_is_current(self, obj) -> bool:
        return obj.id == self.context.get("current_id")


class PublicationSerializer(serializers.Serializer):
    published = serializers.BooleanField()
    published_at = serializers.DateTimeField(allow_null=True)
    withdrawn_at = serializers.DateTimeField(allow_null=True)
    current = ResumeVersionSerializer(allow_null=True)
    history = ResumeVersionSerializer(many=True)


class PublishSerializer(serializers.Serializer):
    external_resume_id = serializers.CharField(max_length=64)


def _job_seeker_only(request):
    if request.user.user_type != "JS":
        return Response(
            {"code": "forbidden", "error": "Only job seekers can publish resumes."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _publication_payload(user):
    publication = ResumePublication.objects.filter(user=user).select_related("version").first()
    current = publication.version if publication else None
    context = {"current_id": current.id if current else None}
    history = ResumeVersion.objects.filter(user=user)[:HISTORY_LIMIT]
    return {
        "published": bool(current),
        "published_at": publication.published_at if current else None,
        "withdrawn_at": publication.withdrawn_at if publication else None,
        "current": ResumeVersionSerializer(current, context=context).data if current else None,
        "history": ResumeVersionSerializer(history, many=True, context=context).data,
    }


@extend_schema(
    tags=TAGS,
    summary="Resumes in the linked Reactive Resume account",
    responses={200: RRResumeSerializer(many=True), 409: RRErrorSerializer, 502: RRErrorSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rr_resumes(request):
    if denied := _guard(request):
        return denied
    try:
        return Response(publishing.list_rr_resumes(request.user))
    except rr_client.RRIntegrationError as exc:
        return _error(exc)


@extend_schema(
    tags=TAGS,
    summary="Published resume",
    description="The current published version (what recruiters see) and recent versions.",
    responses={200: PublicationSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def publication(request):
    if denied := _job_seeker_only(request):
        return denied
    return Response(_publication_payload(request.user))


@extend_schema(
    tags=TAGS,
    summary="Publish a Reactive Resume resume",
    description=(
        "Snapshots the resume (JSON and a PDF of the same stored state) into "
        "private storage and makes it the published version. On any failure "
        "the previous publication stays as it was."
    ),
    request=PublishSerializer,
    responses={
        200: PublicationSerializer,
        404: RRErrorSerializer,
        409: RRErrorSerializer,
        502: RRErrorSerializer,
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def publish(request):
    if denied := _guard(request):
        return denied
    serializer = PublishSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"code": "invalid_request", "error": "Choose a resume to publish."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        publishing.publish(request.user, serializer.validated_data["external_resume_id"])
    except rr_client.RRIntegrationError as exc:
        return _error(exc)
    return Response(_publication_payload(request.user))


@extend_schema(
    tags=TAGS,
    summary="Withdraw the published resume",
    description="Recruiters lose access immediately. Past versions are kept for the job seeker.",
    request=None,
    responses={200: PublicationSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def withdraw(request):
    if denied := _job_seeker_only(request):
        return denied
    publishing.withdraw(request.user)
    return Response(_publication_payload(request.user))


@extend_schema(
    tags=TAGS,
    summary="Download one of your published versions as PDF",
    responses={(200, "application/pdf"): bytes, 404: RRErrorSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def version_pdf(request, version_id):
    if denied := _job_seeker_only(request):
        return denied
    version = ResumeVersion.objects.filter(id=version_id, user=request.user).first()
    if not version:
        return Response({"code": "not_found", "error": "Version not found."}, status=404)
    return _pdf_response(version)


def _pdf_response(version):
    response = FileResponse(
        publishing.open_pdf(version),
        content_type="application/pdf",
        as_attachment=True,
        filename=f"resume-{version.id}.pdf",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
