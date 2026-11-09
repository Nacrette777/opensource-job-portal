"""Job links from the list open the job page (S4-03: slugs carry the id)."""

import io

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.v1.recruiter.tests import make_recruiter
from peeldb.models import Company, JobPost


class JobLinkTests(TestCase):
    def setUp(self):
        call_command("load_gradbridge_locations", stdout=io.StringIO())
        self.recruiter_client = APIClient()
        company = Company.objects.create(name="Acme", slug="acme")
        self.recruiter = make_recruiter("links@acme.test", company, is_admin=True)
        self.recruiter_client.force_authenticate(user=self.recruiter)
        self.client = APIClient()

    def post_job(self, title, live=True, **payload):
        response = self.recruiter_client.post(
            reverse("api:v1:recruiter:jobs-create"),
            {"title": title, "min_year": 0, "max_year": 2, **payload},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        job = JobPost.objects.latest("id")
        if live:
            JobPost.objects.filter(pk=job.pk).update(status="Live")
        return job

    def open(self, slug):
        # The site links to /jobs/<slug without its slashes>/ and asks the API
        # for /jobs/<that>/.
        return self.client.get(
            reverse("api:v1:jobs:job-detail", args=[slug.strip("/")])
        )

    def test_posted_job_has_a_unique_url_safe_slug_that_opens(self):
        first = self.post_job("C# Developer")
        second = self.post_job("C# Developer")
        self.assertEqual(first.slug, f"/c-developer-0-to-2-years-{first.id}/")
        self.assertNotEqual(first.slug, second.slug)
        response = self.open(first.slug)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], first.id)

    def test_editing_the_title_updates_the_slug(self):
        job = self.post_job("Analyst", live=False)  # only drafts can be edited
        response = self.recruiter_client.patch(
            reverse("api:v1:recruiter:jobs-update", args=[job.id]),
            {"title": "Data Analyst"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        job.refresh_from_db()
        self.assertEqual(job.slug, f"/data-analyst-0-to-2-years-{job.id}/")

    def test_legacy_bare_slugs_still_open_and_duplicates_do_not_fail(self):
        for _ in range(2):
            JobPost.objects.create(
                user=self.recruiter,
                title="Python Developer",
                slug="python-developer",
                status="Live",
                vacancies=1,
            )
        response = self.open("python-developer")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["id"], JobPost.objects.order_by("-id").first().id
        )
        self.assertEqual(
            self.open("no-such-job").status_code, status.HTTP_404_NOT_FOUND
        )
