"""Serializers for the GradBridge Reactive Resume integration."""

from rest_framework import serializers

from peeldb.models import ResumeAccountLink


class RRLinkStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField(
        help_text="False when the server has no RR OAuth client configured."
    )
    status = serializers.ChoiceField(
        choices=["not_connected", "connected", "needs_reconnect"]
    )
    rr_email = serializers.CharField(allow_blank=True)
    rr_name = serializers.CharField(allow_blank=True)
    linked_at = serializers.DateTimeField(allow_null=True)
    rr_base_url = serializers.CharField()

    @staticmethod
    def build(link, *, configured, rr_base_url):
        if link and link.status == ResumeAccountLink.STATUS_CONNECTED:
            state = "connected"
        elif link and link.status == ResumeAccountLink.STATUS_ERROR:
            state = "needs_reconnect"
        else:
            state = "not_connected"
        connected = state == "connected"
        return {
            "configured": configured,
            "status": state,
            "rr_email": link.rr_email if connected else "",
            "rr_name": link.rr_name if connected else "",
            "linked_at": link.linked_at if connected else None,
            "rr_base_url": rr_base_url,
        }


class RRConnectResponseSerializer(serializers.Serializer):
    authorization_url = serializers.URLField()


class RRCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=128)
    iss = serializers.CharField(required=False, allow_blank=True, default="")
    error = serializers.CharField(required=False, allow_blank=True, default="")


class RRCheckResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    resume_count = serializers.IntegerField()


class RRErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    error = serializers.CharField()


class RRDraftCreateSerializer(serializers.Serializer):
    request_id = serializers.UUIDField(
        help_text="Client-chosen idempotency key; resubmitting it returns the same draft."
    )


class RRDraftSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    external_resume_id = serializers.CharField(allow_blank=True)
    editor_url = serializers.CharField(allow_blank=True)
    warnings = serializers.ListField(child=serializers.CharField())
    error_code = serializers.CharField(allow_blank=True)
    error = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()

    @staticmethod
    def build(req, editor_url):
        return {
            "id": req.id,
            "status": req.status,
            "external_resume_id": req.external_resume_id,
            "editor_url": editor_url(req.external_resume_id) if req.external_resume_id else "",
            "warnings": req.warnings or [],
            "error_code": req.error_code,
            "error": req.error,
            "created_at": req.created_at,
        }
