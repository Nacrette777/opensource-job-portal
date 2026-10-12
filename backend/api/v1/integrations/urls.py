"""URL routing for the GradBridge Reactive Resume integration."""

from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("rr/", views.rr_status, name="rr-status"),
    path("rr/connect/", views.rr_connect, name="rr-connect"),
    path("rr/callback/", views.rr_callback, name="rr-callback"),
    path("rr/disconnect/", views.rr_disconnect, name="rr-disconnect"),
    path("rr/check/", views.rr_check, name="rr-check"),
    path("rr/drafts/", views.rr_drafts, name="rr-drafts"),
    path("rr/drafts/create/", views.rr_create_draft, name="rr-create-draft"),
]
