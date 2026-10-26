"""Tests for publishing a Reactive Resume resume (S2-06). RR is faked."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from peeldb.models import ResumePublication, ResumeVersion

from . import publishing
from .tests import RRTestBase, make_user

PDF = b"%PDF-1.7\nfake resume\n%%EOF"


class Raw:
    def __init__(self, status_code, body=None, content=b""):
        self.status_code = status_code
        self._body = body
        self.content = content

    def json(self):
        return self._body


class PublicationTests(RRTestBase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="gb-private-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        storage_override = override_settings(GRADBRIDGE_PRIVATE_MEDIA_ROOT=self.tmp)
        storage_override.enable()
        self.addCleanup(storage_override.disable)

        # RR's stored resumes: id -> {"name", "updatedAt", "data"}; updatedAt can
        # be a list to change between reads.
        self.resumes = {
            "res-1": {"name": "Data CV", "updatedAt": "2026-10-12T10:00:00.000Z", "data": {"basics": {"name": "Test"}}},
        }
        self.pdf_status = 200
        self.reads = 0
        original_get = self.rr.get

        def get(url, headers=None, timeout=None):
            path = url.split("http://rr.test", 1)[-1]
            if path == "/api/openapi/resumes":
                return Raw(200, [{"id": k, "name": v["name"], "updatedAt": self._updated(v, peek=True)} for k, v in self.resumes.items()])
            if path.startswith("/api/openapi/resumes/"):
                rest = path[len("/api/openapi/resumes/"):]
                rid, _, tail = rest.partition("/")
                self.rr.gets.append((url, headers))
                resume = self.resumes.get(rid)
                if not resume:
                    return Raw(404, {"code": "NOT_FOUND"})
                if tail == "pdf":
                    return Raw(self.pdf_status, None, PDF if self.pdf_status == 200 else b"")
                return Raw(200, {"id": rid, "name": resume["name"], "updatedAt": self._updated(resume), "data": resume["data"]})
            return original_get(url, headers=headers, timeout=timeout)

        patcher = mock.patch.object(publishing.requests, "get", side_effect=get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _updated(self, resume, peek=False):
        value = resume["updatedAt"]
        if isinstance(value, list):
            if peek:
                return value[0]
            self.reads += 1
            return value[min(self.reads - 1, len(value) - 1)]
        return value

    def publish(self, resume_id="res-1"):
        return self.client.post(
            reverse("api:v1:integrations:publication-publish"),
            {"external_resume_id": resume_id},
            format="json",
        )

    def current(self):
        pub = ResumePublication.objects.filter(user=self.user).first()
        return pub.version if pub else None

    # --- happy path -----------------------------------------------------------

    def test_publish_stores_json_and_pdf_privately_and_moves_the_pointer(self):
        self._linked()

        response = self.publish()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["published"])
        version = self.current()
        self.assertEqual(version.external_resume_id, "res-1")
        self.assertEqual(version.rr_user_id, "rr-user-1")
        self.assertEqual(version.title, "Data CV")
        pdf_path = Path(self.tmp) / version.pdf_key
        self.assertEqual(pdf_path.read_bytes(), PDF)
        self.assertEqual(version.pdf_sha256, hashlib.sha256(PDF).hexdigest())
        stored = json.loads((Path(self.tmp) / version.data_key).read_text(encoding="utf-8"))
        self.assertEqual(stored["data"], {"basics": {"name": "Test"}})
        self.assertEqual(stored["updatedAt"], "2026-10-12T10:00:00.000Z")
        # Every RR read used the job seeker's own bearer token.
        self.assertTrue(all(h["Authorization"].startswith("Bearer access-r") for _, h in self.rr.gets[-3:]))

    def test_lists_resumes_of_the_linked_account(self):
        self._linked()
        response = self.client.get(reverse("api:v1:integrations:rr-resumes"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["id"] for r in response.data], ["res-1"])

    def test_republishing_an_unchanged_resume_reuses_its_version(self):
        self._linked()
        self.publish()
        self.publish()
        self.assertEqual(ResumeVersion.objects.filter(user=self.user).count(), 1)

    def test_a_new_publish_replaces_the_pointer_and_keeps_history(self):
        self._linked()
        self.publish()
        first = self.current()
        self.resumes["res-1"]["updatedAt"] = "2026-10-12T11:00:00.000Z"

        self.publish()

        self.assertNotEqual(self.current().id, first.id)
        response = self.client.get(reverse("api:v1:integrations:publication"))
        self.assertEqual(len(response.data["history"]), 2)
        self.assertEqual(sum(v["is_current"] for v in response.data["history"]), 1)

    # --- consistency and failure keep the old publication ------------------------

    def test_edit_during_rendering_is_retried_until_stable(self):
        self._linked()
        # before / after differ on the first attempt, then stay put
        self.resumes["res-1"]["updatedAt"] = ["t1", "t2", "t2", "t2"]

        response = self.publish()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.current().rr_updated_at, "t2")

    def test_a_resume_that_keeps_changing_is_not_published(self):
        self._linked()
        self.publish()
        old = self.current()
        self.resumes["res-1"]["updatedAt"] = [f"t{i}" for i in range(20)]

        response = self.publish()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "resume_changing")
        self.assertEqual(self.current().id, old.id)

    def test_pdf_failure_keeps_the_previous_publication(self):
        self._linked()
        self.publish()
        old = self.current()
        self.resumes["res-1"]["updatedAt"] = "2026-10-12T12:00:00.000Z"
        self.pdf_status = 500

        response = self.publish()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "pdf_failed")
        self.assertEqual(self.current().id, old.id)
        self.assertEqual(ResumeVersion.objects.count(), 1)

    def test_storage_failure_keeps_the_previous_publication_and_cleans_up(self):
        self._linked()
        self.publish()
        old = self.current()
        self.resumes["res-1"]["updatedAt"] = "2026-10-12T13:00:00.000Z"
        real_save = publishing.FileSystemStorage.save
        calls = {"n": 0}

        def failing_save(storage, name, content, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:  # JSON saved, PDF write fails
                raise OSError("disk full")
            return real_save(storage, name, content, *a, **kw)

        with mock.patch.object(publishing.FileSystemStorage, "save", failing_save):
            response = self.publish()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["code"], "storage_failed")
        self.assertEqual(self.current().id, old.id)
        files = sorted(p.relative_to(self.tmp).as_posix() for p in Path(self.tmp).rglob("*") if p.is_file())
        self.assertEqual(files, sorted([old.data_key, old.pdf_key]))

    def test_unknown_resume_is_not_found(self):
        self._linked()
        response = self.publish("someone-elses")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "resume_not_found")
        self.assertIsNone(self.current())

    def test_requires_a_linked_account(self):
        response = self.publish()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "not_connected")

    # --- withdraw and downloads ------------------------------------------------

    def test_withdraw_clears_the_pointer_but_keeps_versions(self):
        self._linked()
        self.publish()
        version = self.current()

        response = self.client.post(reverse("api:v1:integrations:publication-withdraw"))

        self.assertFalse(response.data["published"])
        self.assertIsNone(self.current())
        self.assertTrue(ResumeVersion.objects.filter(id=version.id).exists())

    def test_owner_downloads_own_version_pdf(self):
        self._linked()
        self.publish()
        version = self.current()

        response = self.client.get(
            reverse("api:v1:integrations:publication-version-pdf", args=[version.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(b"".join(response.streaming_content), PDF)

    def test_another_job_seeker_cannot_download_the_version(self):
        self._linked()
        self.publish()
        version = self.current()
        self.client.force_authenticate(user=make_user("other@example.test"))

        response = self.client.get(
            reverse("api:v1:integrations:publication-version-pdf", args=[version.id])
        )

        self.assertEqual(response.status_code, 404)

    # --- preview before publishing ---------------------------------------------

    def preview(self, resume_id="res-1"):
        return self.client.get(
            reverse("api:v1:integrations:publication-preview-pdf", args=[resume_id])
        )

    def test_preview_returns_the_pdf_rr_renders_now_without_storing_anything(self):
        self._linked()

        response = self.preview()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, PDF)
        self.assertIn("inline", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertFalse(ResumeVersion.objects.exists())
        self.assertIsNone(self.current())
        self.assertEqual(list(Path(self.tmp).rglob("*")), [])

    def test_preview_of_a_resume_outside_the_account_is_not_found(self):
        self._linked()
        response = self.preview("someone-elses")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "resume_not_found")

    def test_preview_rejects_a_malformed_id_without_calling_rr(self):
        self._linked()
        before = len(self.rr.gets)
        response = self.client.get("/api/v1/integrations/publication/preview/res.1%3Fx/pdf/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.rr.gets), before)

    def test_preview_needs_a_linked_account_and_a_job_seeker(self):
        self.assertEqual(self.preview().status_code, 409)
        self.client.force_authenticate(user=make_user("hr2@example.test", user_type="EM"))
        self.assertEqual(self.preview().status_code, 403)

    def test_recruiters_cannot_use_student_publication(self):
        self.client.force_authenticate(user=make_user("hr@example.test", user_type="EM"))
        self.assertEqual(self.client.get(reverse("api:v1:integrations:publication")).status_code, 403)
        self.assertEqual(self.publish().status_code, 403)
