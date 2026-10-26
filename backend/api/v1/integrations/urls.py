"""URL routing for the GradBridge Reactive Resume integration."""

from django.urls import path

from . import publication_views, views

app_name = "integrations"

urlpatterns = [
    path("rr/", views.rr_status, name="rr-status"),
    path("rr/connect/", views.rr_connect, name="rr-connect"),
    path("rr/callback/", views.rr_callback, name="rr-callback"),
    path("rr/disconnect/", views.rr_disconnect, name="rr-disconnect"),
    path("rr/check/", views.rr_check, name="rr-check"),
    path("rr/drafts/", views.rr_drafts, name="rr-drafts"),
    path("rr/drafts/create/", views.rr_create_draft, name="rr-create-draft"),
    path("rr/resumes/", publication_views.rr_resumes, name="rr-resumes"),
    path("publication/", publication_views.publication, name="publication"),
    path("publication/publish/", publication_views.publish, name="publication-publish"),
    path("publication/withdraw/", publication_views.withdraw, name="publication-withdraw"),
    path(
        "publication/preview/<str:external_resume_id>/pdf/",
        publication_views.preview_pdf,
        name="publication-preview-pdf",
    ),
    path(
        "publication/versions/<uuid:version_id>/pdf/",
        publication_views.version_pdf,
        name="publication-version-pdf",
    ),
]
