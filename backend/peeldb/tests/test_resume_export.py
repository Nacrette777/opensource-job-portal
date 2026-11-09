"""Synthetic ORM records only; Django runs these in a separate test database."""

import io
import json
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from unittest import skipUnless

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from peeldb.models import (
    City,
    Country,
    Degree,
    EducationDetails,
    EducationInstitue,
    EmploymentHistory,
    Project,
    Qualification,
    Skill,
    State,
    TechnicalSkill,
    User,
)
from peeldb.resume_export import build_json_resume


class ResumeExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            username="synthetic-student",
            email="synthetic.student@example.com",
            user_type="JS",
            first_name=" 林 ",
            last_name=" 同学 ",
            mobile="+86 13800000000",
            job_role="Software intern",
            profile_description="Synthetic profile for mapping tests.",
            password="must-not-export-password",
            activation_code="must-not-export-activation",
            password_reset_token="must-not-export-token",
            signature="must-not-export-internal-signature",
            resume_text="must-not-export-resume-text",
        )

    def populate(self):
        country = Country.objects.create(name="Synthetic country")
        state = State.objects.create(name="Synthetic region", country=country)
        city = City.objects.create(
            name="Synthetic city", slug="synthetic-city", state=state
        )
        self.user.current_city = city
        self.user.address = "Synthetic street"
        self.user.pincode = 100000
        self.user.save()
        qualification = Qualification.objects.create(name="BSc")
        degree = Degree.objects.create(
            degree_name=qualification, specialization="Computer Science"
        )
        for number in (1, 2):
            institute = EducationInstitue.objects.create(
                name=f"Synthetic school {number}"
            )
            education = EducationDetails.objects.create(
                institute=institute,
                degree=degree,
                from_date=date(2020 + number, 9, 1),
                to_date=date(2024, 6, 30) if number == 1 else None,
                current_education=number == 2,
                score="3.8/4",
            )
            self.user.education.add(education)
            work = EmploymentHistory.objects.create(
                company=f"Synthetic employer {number}",
                designation="Intern",
                job_profile=f"Synthetic responsibility {number}",
                from_date=date(2023 + number, 1, 1),
                to_date=date(2024, 8, 31) if number == 1 else None,
                current_job=number == 2,
            )
            self.user.employment_history.add(work)
            skill = Skill.objects.create(name=f"Synthetic skill {number}")
            self.user.skills.add(
                TechnicalSkill.objects.create(
                    skill=skill, proficiency="Good" if number == 1 else None
                )
            )
            project = Project.objects.create(
                name=f"Synthetic project {number}",
                description=f"Synthetic project description {number}",
                role="Developer" if number == 1 else None,
                from_date=date(2024, 1, 1) if number == 1 else None,
                to_date=date(2024, 6, 30) if number == 1 else None,
                location=city if number == 1 else None,
                size=2 if number == 1 else None,
            )
            project.skills.add(skill)
            self.user.project.add(project)

    def export_command(self, output, **selector):
        stdout, stderr = io.StringIO(), io.StringIO()
        call_command(
            "export_json_resume",
            output=str(output),
            stdout=stdout,
            stderr=stderr,
            **selector,
        )
        return stdout.getvalue(), stderr.getvalue()

    def test_maps_real_relations_multiple_records_and_current_dates(self):
        self.populate()
        result = build_json_resume(self.user)
        data = result.data
        self.assertEqual(data["basics"]["name"], "林 同学")
        self.assertEqual(data["basics"]["email"], self.user.email)
        self.assertEqual(data["basics"]["phone"], self.user.mobile)
        self.assertEqual(data["basics"]["summary"], self.user.profile_description)
        self.assertEqual(data["basics"]["label"], self.user.job_role)
        self.assertEqual(data["basics"]["location"]["city"], "Synthetic city")
        self.assertNotIn("countryCode", data["basics"]["location"])
        for section in ("education", "work", "skills", "projects"):
            self.assertEqual(len(data[section]), 2)
        self.assertEqual(data["education"][0]["institution"], "Synthetic school 1")
        self.assertEqual(data["education"][0]["studyType"], "BSc")
        self.assertEqual(data["education"][0]["area"], "Computer Science")
        self.assertEqual(data["education"][0]["score"], "3.8/4")
        self.assertEqual(data["education"][0]["endDate"], "2024-06-30")
        self.assertNotIn("endDate", data["education"][1])
        self.assertEqual(data["work"][0]["position"], "Intern")
        self.assertEqual(data["work"][0]["summary"], "Synthetic responsibility 1")
        self.assertNotIn("endDate", data["work"][1])
        self.assertEqual(data["skills"][0]["level"], "Advanced")
        self.assertNotIn("level", data["skills"][1])
        self.assertEqual(data["projects"][0]["roles"], ["Developer"])
        self.assertEqual(data["projects"][0]["keywords"], ["Synthetic skill 1"])
        self.assertIn("Role: Developer", data["projects"][0]["highlights"])
        self.assertIn("Skills: Synthetic skill 1", data["projects"][0]["highlights"])
        self.assertNotIn("startDate", data["projects"][1])
        self.assertTrue(any("no ISO code" in warning for warning in result.warnings))

    def test_empty_profile_preserves_detection_without_inventing_name(self):
        self.user.first_name = ""
        self.user.last_name = None
        self.user.email = ""
        self.user.mobile = None
        self.user.job_role = ""
        self.user.profile_description = ""
        result = build_json_resume(self.user)
        self.assertEqual(result.data, {"basics": {}})
        self.assertIn("education: no saved records; omitted.", result.warnings)
        self.assertIn("basics.name: missing; omitted.", result.warnings)

    def test_invalid_email_is_reported_without_leaking_its_value(self):
        self.user.email = "not-an-email"
        result = build_json_resume(self.user)
        self.assertNotIn("email", result.data["basics"])
        self.assertIn("basics.email: invalid email; omitted.", result.warnings)
        self.assertNotIn("not-an-email", str(result))

    def test_unknown_end_date_is_not_fabricated_or_mislabeled_silently(self):
        self.user.employment_history.add(
            EmploymentHistory.objects.create(
                company="Synthetic employer",
                from_date=date(2020, 1, 1),
                current_job=False,
            )
        )
        result = build_json_resume(self.user)
        self.assertNotIn("endDate", result.data["work"][0])
        self.assertTrue(
            any("RR displays Present" in warning for warning in result.warnings)
        )

    def test_missing_start_and_inconsistent_current_end_date(self):
        self.user.employment_history.add(
            EmploymentHistory.objects.create(
                company="Synthetic employer",
                from_date=None,
                to_date=date(2020, 1, 1),
                current_job=True,
            )
        )
        result = build_json_resume(self.user)
        self.assertEqual(result.data["work"], [{"name": "Synthetic employer"}])
        self.assertTrue(any("marked current" in warning for warning in result.warnings))

    def test_skill_levels_match_student_ui_labels(self):
        skill = Skill.objects.create(name="Python")
        entry = TechnicalSkill.objects.create(skill=skill)
        self.user.skills.add(entry)
        for stored, displayed in (
            ("Poor", "Beginner"),
            ("Average", "Intermediate"),
            ("Good", "Advanced"),
            ("Expert", "Expert"),
        ):
            with self.subTest(stored=stored):
                entry.proficiency = stored
                entry.save()
                self.assertEqual(
                    build_json_resume(self.user).data["skills"][0]["level"], displayed
                )

    def test_unrelated_students_records_and_sensitive_fields_are_excluded(self):
        self.populate()
        other = User.objects.create(
            username="other", email="other@example.com", user_type="JS"
        )
        other.employment_history.add(
            EmploymentHistory.objects.create(company="must-not-export-other-company")
        )
        serialized = json.dumps(build_json_resume(self.user).data)
        self.assertNotIn("must-not-export", serialized)
        self.assertNotIn("sections", serialized)
        self.assertNotIn("metadata", serialized)
        self.assertNotIn("user_id", serialized)
        self.assertNotIn("username", serialized)

    def test_requires_exactly_one_explicit_selector(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "resume.json"
            for selector in ({}, {"user_id": self.user.pk, "email": self.user.email}):
                with (
                    self.subTest(selector=list(selector)),
                    self.assertRaises(CommandError),
                ):
                    self.export_command(output, **selector)
                self.assertFalse(output.exists())

    def test_unknown_student_does_not_fall_back_to_any_user(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "resume.json"
            with self.assertRaisesMessage(CommandError, "does not exist"):
                self.export_command(output, user_id=self.user.pk + 999999)
            self.assertFalse(output.exists())

    def test_recruiter_is_rejected(self):
        self.user.user_type = "EM"
        self.user.save()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "resume.json"
            with self.assertRaisesMessage(CommandError, "Only a job seeker"):
                self.export_command(output, user_id=self.user.pk)
            self.assertFalse(output.exists())

    def test_ambiguous_case_insensitive_email_requires_id(self):
        User.objects.create(
            username="duplicate-case", email=self.user.email.upper(), user_type="JS"
        )
        with (
            tempfile.TemporaryDirectory() as folder,
            self.assertRaisesMessage(CommandError, "ambiguous"),
        ):
            self.export_command(Path(folder) / "resume.json", email=self.user.email)

    def test_utf8_export_by_id_and_email_has_no_database_writes_or_personal_logs(self):
        self.populate()
        with tempfile.TemporaryDirectory() as folder:
            for index, selector in enumerate(
                ({"user_id": self.user.pk}, {"email": self.user.email.upper()})
            ):
                output = Path(folder) / f"resume-{index}.json"
                with CaptureQueriesContext(connection) as queries:
                    stdout, stderr = self.export_command(output, **selector)
                self.assertTrue(
                    all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries)
                )
                self.assertEqual(
                    json.loads(output.read_text(encoding="utf-8")),
                    build_json_resume(self.user).data,
                )
                self.assertFalse(output.read_bytes().startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(self.user.email, stdout + stderr)
                self.assertNotIn("林", stdout + stderr)

    def test_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "resume.json"
            output.write_text("keep existing file", encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "Cannot create output"):
                self.export_command(output, user_id=self.user.pk)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep existing file")

    @skipUnless(
        os.environ.get("REACTIVE_RESUME_DIR"),
        "Set REACTIVE_RESUME_DIR for RR compatibility test",
    )
    def test_actual_rr_ui_importer_accepts_populated_and_empty_exports(self):
        rr_root = Path(os.environ["REACTIVE_RESUME_DIR"])
        portal_root = Path(__file__).resolve().parents[3]
        validator = portal_root / "tools" / "validate_resume_import.mjs"
        loader = (rr_root / "apps/server/node_modules/tsx/dist/loader.mjs").as_uri()
        self.populate()
        with tempfile.TemporaryDirectory() as folder:
            for populated in (True, False):
                if not populated:
                    self.user.education.clear()
                    self.user.employment_history.clear()
                    self.user.skills.clear()
                    self.user.project.clear()
                    self.user.first_name = ""
                    self.user.last_name = None
                    self.user.mobile = None
                    self.user.profile_description = ""
                    self.user.save()
                output = Path(folder) / f"synthetic-{populated}.json"
                self.export_command(output, user_id=self.user.pk)
                completed = subprocess.run(
                    [
                        "node",
                        "--import",
                        loader,
                        str(validator),
                        "--rr-root",
                        str(rr_root),
                        "--input",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads(completed.stdout)
                self.assertTrue(report["accepted"])
                self.assertEqual(report["counts"]["education"], 2 if populated else 0)
