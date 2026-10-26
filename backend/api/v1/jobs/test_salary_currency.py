"""GradBridge localisation: salaries in AUD or SGD, shown and filtered as yearly amounts."""

import io

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.v1.jobs.serializers import JobListSerializer, thousands
from api.v1.recruiter.tests import make_recruiter
from peeldb.models import City, Company, JobPost


def make_job(user, title, **fields):
    return JobPost.objects.create(
        user=user,
        title=title,
        slug=f"/{title.lower().replace(' ', '-')}/",
        status="Live",
        vacancies=1,
        **fields,
    )


class SalaryDisplayTests(TestCase):
    def setUp(self):
        self.recruiter = make_recruiter("pay@acme.test")

    def display(self, **fields):
        return JobListSerializer(make_job(self.recruiter, "Role", **fields)).data["salary_display"]

    def test_yearly_range_in_australian_dollars(self):
        self.assertEqual(
            self.display(min_salary=85000, max_salary=95000, salary_type="Year", salary_currency="AUD"),
            "A$85k–95k a year",
        )

    def test_monthly_salary_is_shown_per_year_in_singapore_dollars(self):
        self.assertEqual(
            self.display(min_salary=5000, max_salary=6500, salary_type="Month", salary_currency="SGD"),
            "S$60k–78k a year",
        )

    def test_open_ended_and_undisclosed(self):
        self.assertEqual(self.display(max_salary=70000, salary_type="Year"), "Up to A$70k a year")
        self.assertEqual(self.display(min_salary=70000, salary_type="Year"), "From A$70k a year")
        self.assertEqual(self.display(), "Not Disclosed")

    def test_no_rupees_or_lakhs(self):
        text = self.display(min_salary=500000, max_salary=800000, salary_type="Year")
        self.assertNotIn("₹", text)
        self.assertNotIn("LPA", text)

    def test_thousands(self):
        self.assertEqual(thousands(92500), "92.5k")
        self.assertEqual(thousands(800), "800")


class SalaryFilterTests(TestCase):
    """`min_salary` / `max_salary` are thousands a year (80 = 80,000), not lakhs."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("api:v1:jobs:job-list")
        recruiter = make_recruiter("filter@acme.test")
        make_job(recruiter, "Junior", min_salary=60000, max_salary=70000, salary_type="Year")
        make_job(recruiter, "Senior", min_salary=120000, max_salary=140000, salary_type="Year")
        make_job(recruiter, "Monthly", min_salary=8000, max_salary=9000, salary_type="Month")

    def titles(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return sorted(job["title"] for job in response.data["results"])

    def test_min_salary_in_thousands(self):
        self.assertEqual(self.titles(min_salary=100), ["Monthly", "Senior"])

    def test_max_salary_in_thousands(self):
        self.assertEqual(self.titles(max_salary=80), ["Junior"])


class DefaultCurrencyTests(TestCase):
    """A new job's currency follows its cities unless the recruiter picks one."""

    def setUp(self):
        call_command("load_gradbridge_locations", stdout=io.StringIO())
        self.client = APIClient()
        company = Company.objects.create(name="Acme", slug="acme")
        self.client.force_authenticate(user=make_recruiter("post@acme.test", company, is_admin=True))
        self.singapore = City.objects.get(slug="singapore")
        self.sydney = City.objects.get(slug="sydney")

    def create(self, title, **payload):
        response = self.client.post(
            reverse("api:v1:recruiter:jobs-create"), {"title": title, **payload}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return JobPost.objects.get(title=title)

    def test_singapore_job_defaults_to_sgd(self):
        self.assertEqual(self.create("SG role", location_ids=[self.singapore.id]).salary_currency, "SGD")

    def test_australian_or_mixed_job_defaults_to_aud(self):
        self.assertEqual(self.create("AU role", location_ids=[self.sydney.id]).salary_currency, "AUD")
        self.assertEqual(
            self.create("Both", location_ids=[self.sydney.id, self.singapore.id]).salary_currency, "AUD"
        )
        self.assertEqual(self.create("Nowhere").salary_currency, "AUD")

    def test_recruiter_choice_wins(self):
        job = self.create("Chosen", location_ids=[self.sydney.id], salary_currency="SGD")
        self.assertEqual(job.salary_currency, "SGD")

    def test_editing_a_draft_can_change_the_currency(self):
        job = self.create("Draft", location_ids=[self.sydney.id])
        response = self.client.patch(
            reverse("api:v1:recruiter:jobs-update", args=[job.id]), {"salary_currency": "SGD"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        job.refresh_from_db()
        self.assertEqual(job.salary_currency, "SGD")

    def test_unknown_currency_is_rejected(self):
        response = self.client.post(
            reverse("api:v1:recruiter:jobs-create"), {"title": "Rupees", "salary_currency": "INR"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
