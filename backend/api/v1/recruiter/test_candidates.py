"""Tests for GradBridge recruiter candidate search, shortlist and notes (S2-07)."""

import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from peeldb.models import (
    CandidateNote,
    Company,
    Degree,
    EducationDetails,
    EducationInstitue,
    Project,
    Qualification,
    ResumePublication,
    ResumeVersion,
    Skill,
    TechnicalSkill,
    User,
)

PDF = b"%PDF-1.7\ncandidate resume\n%%EOF"


class CandidateTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gb-candidates-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        storage = override_settings(GRADBRIDGE_PRIVATE_MEDIA_ROOT=self.tmp)
        storage.enable()
        self.addCleanup(storage.disable)

        self.python = Skill.objects.create(name="Python", status="Active", slug="python")
        self.sql = Skill.objects.create(name="SQL", status="Active", slug="sql")
        bachelor = Qualification.objects.create(name="Bachelor", status="Active", slug="bachelor")
        master = Qualification.objects.create(name="Master", status="Active", slug="master")
        self.bachelor = bachelor
        self.cs = Degree.objects.create(degree_name=bachelor, degree_type="Permanent", specialization="Computer Science")
        self.ds = Degree.objects.create(degree_name=master, degree_type="Permanent", specialization="Data Science")
        self.uni = EducationInstitue.objects.create(name="Test University")

        self.s1 = self.student("s1@example.test", "Ada", skills=[self.python, self.sql], education=[(self.cs, 2024)])
        self.s1.mobile = "+61 400000001"
        self.s1.address = "1 Private Street"
        self.s1.alternate_mobile = "0499000111"
        self.s1.pincode = "0800"
        self.s1.dob = date(2002, 1, 1)
        self.s1.save()
        self.s1.project.add(Project.objects.create(name="Sales Dashboard", description="BI"))
        self.s2 = self.student("s2@example.test", "Ben", skills=[self.python], education=[(self.cs, 2019), (self.ds, 2024)])
        self.s2.show_email = True
        self.s2.save()
        self.s3 = self.student("s3@example.test", "Cat", skills=[self.python, self.sql], education=[(self.cs, 2024)])
        self.publish(self.s1)
        self.publish(self.s2)  # s3 stays unpublished

        company_a = Company.objects.create(name="A", address="x", profile="x", phone_number="1", slug="a")
        company_b = Company.objects.create(name="B", address="x", profile="x", phone_number="1", slug="b")
        self.a1 = self.recruiter("a1@example.test", company_a, admin=True)
        self.a2 = self.recruiter("a2@example.test", company_a)
        self.b1 = self.recruiter("b1@example.test", company_b, admin=True)
        self.client = APIClient()
        self.client.force_authenticate(self.a1)

    # --- fixtures -----------------------------------------------------------

    def student(self, email, first, skills, education):
        user = User.objects.create_user(username=email, email=email, password="Str0ng!Passw0rd")
        user.user_type = "JS"
        user.is_active = True
        user.first_name = first
        user.last_name = "Student"
        user.job_role = "Data Analyst"
        user.save()
        for skill in skills:
            user.skills.add(TechnicalSkill.objects.create(skill=skill, proficiency="Good", year=1))
        for degree, year in education:
            user.education.add(
                EducationDetails.objects.create(
                    institute=self.uni, degree=degree, from_date=date(year - 3, 2, 1), to_date=date(year, 11, 30), score="A"
                )
            )
        return user

    def publish(self, user, content=PDF):
        key = f"resumes/{user.id}/{ResumeVersion.objects.count()}/resume.pdf"
        path = Path(self.tmp) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        version = ResumeVersion.objects.create(
            user=user, rr_user_id="rr", external_resume_id="r", title="CV", rr_updated_at="t",
            data_key=key, data_sha256="x", pdf_key=key, pdf_sha256="x", pdf_size=len(content),
        )
        pub, _ = ResumePublication.objects.get_or_create(user=user)
        pub.version = version
        pub.save()
        return version

    def recruiter(self, email, company, admin=False):
        user = User.objects.create_user(username=email, email=email, password="Str0ng!Passw0rd")
        user.user_type = "EM"
        user.is_active = True
        user.company = company
        user.is_admin = admin
        user.save()
        return user

    def search(self, **params):
        response = self.client.get(reverse("api:v1:recruiter:candidates"), params)
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return sorted(r["id"] for r in response.data["results"])

    def withdraw(self, user):
        ResumePublication.objects.filter(user=user).update(version=None)

    # --- access ----------------------------------------------------------------

    def test_anonymous_and_job_seekers_are_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("api:v1:recruiter:candidates")).status_code, 401)
        self.client.force_authenticate(self.s1)
        self.assertEqual(self.client.get(reverse("api:v1:recruiter:candidates")).status_code, 403)
        url = reverse("api:v1:recruiter:candidate-resume-pdf", args=[self.s2.id])
        self.assertEqual(self.client.get(url).status_code, 403)

    # --- search -----------------------------------------------------------------

    def test_only_published_job_seekers_are_candidates(self):
        self.assertEqual(self.search(), sorted([self.s1.id, self.s2.id]))

    def test_all_selected_skills_must_match(self):
        self.assertEqual(self.search(skills=f"{self.python.id},{self.sql.id}"), [self.s1.id])
        self.assertEqual(self.search(skills=str(self.python.id)), sorted([self.s1.id, self.s2.id]))

    def test_qualification_and_year_must_hold_for_the_same_education(self):
        # s2 has a Bachelor (2019) and a Master (2024): not a "Bachelor graduating 2024".
        self.assertEqual(self.search(qualification=self.bachelor.id, graduation_year=2024), [self.s1.id])
        self.assertEqual(self.search(degree=self.ds.id), [self.s2.id])

    def test_keyword_matches_name_role_and_projects(self):
        self.assertEqual(self.search(q="dashboard"), [self.s1.id])
        self.assertEqual(self.search(q="ben"), [self.s2.id])

    def test_malformed_filters_are_rejected(self):
        for params in ({"skills": "python"}, {"graduation_year": "1800"}, {"qualification": "x"}):
            response = self.client.get(reverse("api:v1:recruiter:candidates"), params)
            self.assertEqual(response.status_code, 400, params)

    # --- detail and download ----------------------------------------------------

    def test_detail_leaves_out_private_contact_details(self):
        data = self.client.get(reverse("api:v1:recruiter:candidate-detail", args=[self.s1.id])).data
        self.assertEqual(data["name"], "Ada Student")
        self.assertIsNone(data["email"])  # show_email is off
        flat = str(data)
        for secret in ("+61 400000001", "0499000111", "1 Private Street", "0800", "2002-01-01"):
            self.assertNotIn(secret, flat)
        self.assertEqual([s["name"] for s in data["skills"]], ["Python", "SQL"])
        self.assertEqual(data["projects"][0]["name"], "Sales Dashboard")

        shown = self.client.get(reverse("api:v1:recruiter:candidate-detail", args=[self.s2.id])).data
        self.assertEqual(shown["email"], "s2@example.test")

    def test_unpublished_candidate_is_not_found(self):
        self.assertEqual(self.client.get(reverse("api:v1:recruiter:candidate-detail", args=[self.s3.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("api:v1:recruiter:candidate-resume-pdf", args=[self.s3.id])).status_code, 404)

    def test_pdf_is_the_current_published_version(self):
        url = reverse("api:v1:recruiter:candidate-resume-pdf", args=[self.s1.id])
        first = self.client.get(url)
        self.assertEqual(b"".join(first.streaming_content), PDF)
        self.assertIn("no-store", first["Cache-Control"])

        self.publish(self.s1, content=b"%PDF-1.7\nnew version\n%%EOF")
        self.assertEqual(b"".join(self.client.get(url).streaming_content), b"%PDF-1.7\nnew version\n%%EOF")

    def test_withdrawing_removes_access_immediately(self):
        detail = reverse("api:v1:recruiter:candidate-detail", args=[self.s1.id])
        pdf = reverse("api:v1:recruiter:candidate-resume-pdf", args=[self.s1.id])
        self.assertEqual(self.client.get(pdf).status_code, 200)

        self.withdraw(self.s1)

        self.assertEqual(self.search(), [self.s2.id])
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(self.client.get(pdf).status_code, 404)

    # --- shortlist and notes are private to each recruiter -------------------------

    def test_shortlist_is_per_recruiter(self):
        url = reverse("api:v1:recruiter:candidate-shortlist", args=[self.s1.id])
        self.assertEqual(self.client.post(url).data, {"shortlisted": True})

        mine = self.client.get(reverse("api:v1:recruiter:candidate-shortlist-list")).data
        self.assertEqual([r["id"] for r in mine["results"]], [self.s1.id])
        for other in (self.a2, self.b1):  # same company, other company
            self.client.force_authenticate(other)
            self.assertEqual(self.client.get(reverse("api:v1:recruiter:candidate-shortlist-list")).data["count"], 0)
            listed = self.client.get(reverse("api:v1:recruiter:candidates")).data["results"]
            self.assertFalse(any(r["shortlisted"] for r in listed))

    def test_shortlisted_candidate_who_withdraws_shows_nothing(self):
        self.client.post(reverse("api:v1:recruiter:candidate-shortlist", args=[self.s1.id]))
        self.withdraw(self.s1)

        entry = self.client.get(reverse("api:v1:recruiter:candidate-shortlist-list")).data["results"][0]

        self.assertEqual(entry["available"], False)
        self.assertNotIn("name", entry)
        removed = self.client.delete(reverse("api:v1:recruiter:candidate-shortlist", args=[self.s1.id]))
        self.assertEqual(removed.data, {"shortlisted": False})

    def test_unpublished_candidate_cannot_be_shortlisted(self):
        response = self.client.post(reverse("api:v1:recruiter:candidate-shortlist", args=[self.s3.id]))
        self.assertEqual(response.status_code, 404)

    def test_notes_are_visible_only_to_their_author(self):
        notes_url = reverse("api:v1:recruiter:candidate-notes", args=[self.s1.id])
        note = self.client.post(notes_url, {"body": "Strong SQL; call back"}, format="json").data
        self.assertEqual(self.client.get(notes_url).data[0]["body"], "Strong SQL; call back")
        listed = self.client.get(reverse("api:v1:recruiter:candidates")).data["results"]
        self.assertEqual({r["id"]: r["note_count"] for r in listed}[self.s1.id], 1)

        note_url = reverse("api:v1:recruiter:candidate-note-detail", args=[self.s1.id, note["id"]])
        for other in (self.a2, self.b1):
            self.client.force_authenticate(other)
            self.assertEqual(self.client.get(notes_url).data, [])
            self.assertEqual(self.client.patch(note_url, {"body": "hijack"}, format="json").status_code, 404)
            self.assertEqual(self.client.delete(note_url).status_code, 404)
        self.assertEqual(CandidateNote.objects.get(id=note["id"]).body, "Strong SQL; call back")

        self.client.force_authenticate(self.a1)
        self.assertEqual(self.client.patch(note_url, {"body": "Interview booked"}, format="json").data["body"], "Interview booked")
        self.assertEqual(self.client.delete(note_url).status_code, 204)

    def test_empty_note_is_rejected(self):
        response = self.client.post(
            reverse("api:v1:recruiter:candidate-notes", args=[self.s1.id]), {"body": "   "}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_filter_options(self):
        data = self.client.get(reverse("api:v1:recruiter:candidate-filters")).data
        self.assertEqual([s["name"] for s in data["skills"]], ["Python", "SQL"])
        self.assertEqual(data["graduation_years"], [2024, 2019])
