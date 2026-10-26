"""
GradBridge: recruiter candidate search, detail, published PDF, shortlist and
private notes (S2-07).

Every candidate-specific request re-checks `candidate_pool()`, so a job seeker
who withdraws their resume disappears from search, detail and download at
once. Shortlists and notes belong to the individual recruiter: colleagues in
the same company do not see them.
"""

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.v1.integrations import publishing
from peeldb.models import (
    CandidateNote,
    CandidateShortlist,
    Degree,
    Qualification,
    Skill,
)

from . import candidates

TAGS = ["Recruiter Candidates"]

ERROR = inline_serializer("CandidateError", {"code": serializers.CharField(), "error": serializers.CharField()})


class CandidatePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateNote
        fields = ["id", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Note cannot be empty")
        return value


def _forbidden():
    return Response(
        {"code": "forbidden", "error": "Only recruiters can use candidate search."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _not_found():
    return Response(
        {"code": "not_found", "error": "Candidate not found or no longer available."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _candidate(candidate_id):
    return candidates.candidate_pool().select_related("resume_publication__version").filter(id=candidate_id).first()


@extend_schema(
    tags=TAGS,
    summary="Search candidates",
    description=(
        "Job seekers with a published resume. `skills` is a comma-separated "
        "list of skill ids that must ALL be on the profile; qualification, "
        "degree and graduation_year must match the same education entry."
    ),
    parameters=[
        OpenApiParameter("q", str),
        OpenApiParameter("skills", str),
        OpenApiParameter("qualification", int),
        OpenApiParameter("degree", int),
        OpenApiParameter("graduation_year", int),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int),
    ],
    responses={200: dict, 400: ERROR, 403: ERROR},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_candidates(request):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    try:
        qs = candidates.search(request.query_params)
    except candidates.InvalidFilter as exc:
        return Response({"code": "invalid_filter", "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    paginator = CandidatePagination()
    page = paginator.paginate_queryset(candidates.with_list_data(qs), request)
    shortlisted, counts = candidates.list_context(request.user, [u.id for u in page])
    return paginator.get_paginated_response(
        [candidates.list_item(u, request.user, shortlisted, counts) for u in page]
    )


@extend_schema(tags=TAGS, summary="Candidate search filter options", responses={200: dict, 403: ERROR})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def candidate_filters(request):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    pool = candidates.candidate_pool()
    years = sorted(
        {d.year for d in pool.values_list("education__to_date", flat=True) if d},
        reverse=True,
    )
    return Response(
        {
            "skills": list(Skill.objects.filter(status="Active").order_by("name").values("id", "name")),
            "qualifications": list(
                Qualification.objects.filter(status="Active").order_by("name").values("id", "name")
            ),
            "degrees": [
                {"id": d.id, "name": f"{d.degree_name.name} — {d.specialization}", "qualification_id": d.degree_name_id}
                for d in Degree.objects.select_related("degree_name").order_by("degree_name__name", "specialization")
            ],
            "graduation_years": years,
        }
    )


@extend_schema(tags=TAGS, summary="Candidate detail", responses={200: dict, 403: ERROR, 404: ERROR})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def candidate_detail(request, candidate_id):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    user = _candidate(candidate_id)
    if not user:
        return _not_found()
    return Response(candidates.detail(user, request.user))


@extend_schema(
    tags=TAGS,
    summary="Download the candidate's published resume PDF",
    responses={(200, "application/pdf"): bytes, 403: ERROR, 404: ERROR},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def candidate_resume_pdf(request, candidate_id):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    user = _candidate(candidate_id)
    if not user:
        return _not_found()
    version = user.resume_publication.version
    response = FileResponse(
        publishing.open_pdf(version),
        content_type="application/pdf",
        as_attachment=True,
        filename=f"candidate-{user.id}-resume.pdf",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema(tags=TAGS, summary="Shortlist or un-shortlist a candidate", request=None, responses={200: dict, 404: ERROR})
@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def candidate_shortlist(request, candidate_id):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    if request.method == "DELETE":
        # Allowed even after the candidate withdrew, so a shortlist can be tidied.
        CandidateShortlist.objects.filter(recruiter=request.user, candidate_id=candidate_id).delete()
        return Response({"shortlisted": False})
    user = _candidate(candidate_id)
    if not user:
        return _not_found()
    CandidateShortlist.objects.get_or_create(recruiter=request.user, candidate=user)
    return Response({"shortlisted": True})


@extend_schema(tags=TAGS, summary="Your shortlisted candidates", responses={200: dict, 403: ERROR})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_shortlist(request):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    entries = list(CandidateShortlist.objects.filter(recruiter=request.user))
    available = {
        u.id: u
        for u in candidates.candidate_pool()
        .select_related("resume_publication")
        .filter(id__in=[e.candidate_id for e in entries])
    }
    shortlisted, counts = candidates.list_context(request.user, list(available))
    results = []
    for entry in entries:
        user = available.get(entry.candidate_id)
        if user:
            item = candidates.list_item(user, request.user, shortlisted, counts)
            item.update(available=True, shortlisted_at=entry.created_at)
        else:
            # Withdrawn: nothing about the candidate is shown any more.
            item = {"id": entry.candidate_id, "available": False, "shortlisted_at": entry.created_at}
        results.append(item)
    return Response({"count": len(results), "results": results})


@extend_schema(
    tags=TAGS,
    summary="Your private notes on a candidate",
    request=NoteSerializer,
    responses={200: NoteSerializer(many=True), 201: NoteSerializer, 400: dict, 404: ERROR},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def candidate_notes(request, candidate_id):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    user = _candidate(candidate_id)
    if not user:
        return _not_found()
    if request.method == "GET":
        notes = CandidateNote.objects.filter(recruiter=request.user, candidate=user)
        return Response(NoteSerializer(notes, many=True).data)
    serializer = NoteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    note = serializer.save(recruiter=request.user, candidate=user)
    return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=TAGS,
    summary="Edit or delete one of your notes",
    request=NoteSerializer,
    responses={200: NoteSerializer, 204: None, 404: ERROR},
)
@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def candidate_note_detail(request, candidate_id, note_id):
    if not candidates.is_recruiter(request.user):
        return _forbidden()
    # Author-only: another recruiter's note is indistinguishable from a missing one.
    note = get_object_or_404(CandidateNote, id=note_id, candidate_id=candidate_id, recruiter=request.user)
    if request.method == "DELETE":
        note.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if not _candidate(candidate_id):
        return _not_found()
    serializer = NoteSerializer(note, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)
