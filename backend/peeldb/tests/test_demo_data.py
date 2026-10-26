"""Initial data and the demo-data generators produce Singapore/Australia data, not Indian."""

import io
import re

from django.core.management import call_command
from django.test import TestCase

from peeldb.management.commands.load_gradbridge_reference_data import (
    LANGUAGES,
    QUALIFICATIONS,
)
from peeldb.models import (
    City,
    Company,
    Country,
    EducationInstitue,
    JobPost,
    Language,
    Qualification,
    User,
)

INDIAN = re.compile(
    r"India|Bangalore|Bengaluru|Hyderabad|Mumbai|Chennai|Pune|Delhi|Kolkata|Noida|Gurgaon|Telangana|Pvt Ltd|\+91"
)


def run(*args, **options):
    out = io.StringIO()
    call_command(*args, stdout=out, **options)
    return out.getvalue()


class InitialDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        run("load_initial_data")

    def test_locations_are_singapore_and_australia_only(self):
        self.assertEqual(sorted(Country.objects.values_list("name", flat=True)), ["Australia", "Singapore"])
        self.assertFalse(City.objects.filter(name__in=["Hyderabad", "Bangalore", "Mumbai"]).exists())

    def test_qualifications_and_languages_are_the_gradbridge_lists(self):
        self.assertEqual(sorted(Qualification.objects.values_list("name", flat=True)), sorted(QUALIFICATIONS))
        self.assertEqual(sorted(Language.objects.values_list("name", flat=True)), sorted(LANGUAGES))
        self.assertFalse(Qualification.objects.filter(name__in=["B.Tech", "MCA", "10th pass"]).exists())

    def test_reference_data_is_idempotent(self):
        counts = (Qualification.objects.count(), Language.objects.count())
        output = run("load_gradbridge_reference_data")
        self.assertEqual((Qualification.objects.count(), Language.objects.count()), counts)
        self.assertIn("created 0", output)


class CreateTestDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        run("load_initial_data")
        run("create_test_data", companies=4, recruiters=6, jobseekers=8, jobs=25, applications=10)

    def test_no_indian_names_places_or_numbers(self):
        texts = []
        for company in Company.objects.all():
            texts += [company.name, company.address, company.phone_number or ""]
        for user in User.objects.all():
            texts += [user.mobile or "", user.email]
        texts += list(EducationInstitue.objects.values_list("name", flat=True))
        self.assertEqual([t for t in texts if INDIAN.search(t)], [])

    def test_phone_numbers_match_the_users_country(self):
        for user in User.objects.exclude(mobile=""):
            prefix = "+65" if user.country.slug == "singapore" else "+614"
            self.assertTrue(user.mobile.startswith(prefix), (user.mobile, user.country.name))

    def test_emails_have_no_spaces(self):
        self.assertFalse(User.objects.filter(email__contains=" ").exists())

    def test_each_job_stays_in_one_country_and_uses_its_currency(self):
        jobs = JobPost.objects.prefetch_related("location__state__country")
        self.assertEqual(jobs.count(), 25)
        for job in jobs:
            countries = {city.state.country.slug for city in job.location.all()}
            self.assertEqual(len(countries), 1, job.title)
            expected = "SGD" if countries == {"singapore"} else "AUD"
            self.assertEqual(job.salary_currency, expected)
            self.assertEqual(job.country.slug, countries.pop())
            self.assertGreaterEqual(job.min_salary, 48000)
            self.assertLessEqual(job.max_salary, 260000)


class CreateTestUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        run("load_initial_data")
        run("create_test_users")

    def test_jobs_are_in_sydney_melbourne_brisbane_perth_or_singapore(self):
        cities = set(JobPost.objects.values_list("location__name", flat=True))
        self.assertTrue(cities <= {"Sydney", "Melbourne", "Brisbane", "Perth", "Singapore"}, cities)

    def test_singapore_jobs_are_in_sgd_and_the_rest_in_aud(self):
        for job in JobPost.objects.prefetch_related("location"):
            in_singapore = job.location.filter(slug="singapore").exists()
            self.assertEqual(job.salary_currency, "SGD" if in_singapore else "AUD", job.title)
            self.assertLess(job.max_salary, 300000, job.title)

    def test_job_seeker_profile_is_local(self):
        seeker = User.objects.get(user_type="JS")
        self.assertEqual(seeker.city.name, "Sydney")
        self.assertTrue(seeker.mobile.startswith("+61"))
        self.assertEqual(seeker.education.get().institute.name, "UNSW Sydney")
        self.assertEqual(sorted(seeker.language.values_list("language__name", flat=True)), ["English", "Mandarin"])
