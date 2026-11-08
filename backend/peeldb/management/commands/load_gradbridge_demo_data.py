"""
Clearly labelled demo companies and jobs for a GradBridge deployment (S4-03).

    python manage.py load_gradbridge_demo_data            # 8 companies, 5 live jobs each
    python manage.py load_gradbridge_demo_data --remove   # delete everything it created

create_test_data is for development only: its accounts share a password that
is committed to the repository, and its websites, emails and phone numbers
look real. This command reuses its generators but is safe on a public site:

- every company name ends in "(Demo)" and every company profile and job
  description starts with a notice that it is not real;
- the recruiter accounts that own the jobs cannot sign in (unusable password,
  example.test addresses), and no website, email or phone number is set
  that could belong to someone;
- everything carries DEMO_MARKER, so --remove finds it, and running the
  command again replaces the previous set rather than adding to it.

Needs the reference data first (python manage.py load_initial_data).
"""

import io

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from peeldb.models import City, Company, Industry, JobPost, Qualification, Skill, User

from .create_test_data import Command as TestDataCommand
from .test_data.constants import TEST_DATA_MARKER, USER_TYPE_EMPLOYER

DEMO_MARKER = "[GRADBRIDGE DEMO]"
DEMO_SUFFIX = " (Demo)"
COMPANY_NOTICE = (
    "<p><strong>Demo company.</strong> This employer was generated to show how "
    "GradBridge works. It is not a real organisation.</p>"
)
JOB_NOTICE = (
    "<p><strong>Demo listing.</strong> This job was generated to show how "
    "GradBridge works. It is not a real vacancy: applications reach no employer.</p>"
)


def remove_demo_data():
    """Delete the demo jobs, their recruiters and companies; returns the counts."""
    jobs = JobPost.objects.filter(meta_description__contains=DEMO_MARKER)
    users = User.objects.filter(
        user_type=USER_TYPE_EMPLOYER, profile_description__contains=DEMO_MARKER
    )
    companies = Company.objects.filter(profile__contains=DEMO_MARKER)
    counts = (jobs.count(), users.count(), companies.count())
    # Applications to demo jobs (and the recruiters' own records) go with them.
    jobs.delete()
    users.delete()
    companies.delete()
    return counts


class Command(BaseCommand):
    help = "Create (or with --remove, delete) labelled demo companies and jobs."

    def add_arguments(self, parser):
        parser.add_argument("--companies", type=int, default=8)
        parser.add_argument("--jobs-per-company", type=int, default=5)
        parser.add_argument(
            "--remove", action="store_true", help="Only delete the demo data."
        )

    @transaction.atomic
    def handle(self, *args, **options):
        jobs, users, companies = remove_demo_data()
        if jobs or users or companies:
            self.stdout.write(
                f"Removed {jobs} demo jobs, {users} demo recruiters, {companies} demo companies."
            )
        if options["remove"]:
            return

        generator = TestDataCommand(stdout=io.StringIO())
        generator._validate_fixtures_loaded()
        cities = list(
            City.objects.filter(status="Enabled").select_related("state__country")
        )
        by_country = {}
        for city in cities:
            by_country.setdefault(city.state.country.slug, []).append(city)
        generator.skills = list(Skill.objects.filter(status="Active"))
        generator.industries = list(Industry.objects.filter(status="Active"))
        generator.qualifications = list(Qualification.objects.all())

        total_jobs = 0
        for i in range(options["companies"]):
            # One country per company, so a "Pte. Ltd." does not advertise in
            # Perth; every fourth company is in Singapore when it is loaded.
            country = "singapore" if i % 4 == 3 and "singapore" in by_country else None
            generator.cities = by_country.get(country) or by_country.get(
                "australia", cities
            )
            company = generator._create_companies(1)[0]
            self._label_company(company)
            recruiter = generator._create_recruiters(1, [company])[0]
            self._label_recruiter(recruiter)
            for job in generator._create_jobs(
                options["jobs_per_company"], [recruiter], [company]
            ):
                self._label_job(job, company)
                total_jobs += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {options['companies']} demo companies (one recruiter each, "
                f"who cannot sign in) and {total_jobs} live demo jobs. "
                "Remove them with --remove."
            )
        )

    def _label_company(self, company):
        profile = company.profile.replace(TEST_DATA_MARKER, DEMO_MARKER)
        company.name = f"{company.name}{DEMO_SUFFIX}"
        company.slug = f"{slugify(company.name)}-{company.pk}"
        company.profile = COMPANY_NOTICE + profile
        company.website = ""
        company.email = None
        company.phone_number = ""
        company.save()

    def _label_recruiter(self, user):
        user.set_unusable_password()
        user.profile_description = user.profile_description.replace(
            TEST_DATA_MARKER, DEMO_MARKER
        )
        user.mobile = None
        user.save()

    def _label_job(self, job, company):
        job.status = "Live"
        job.description = JOB_NOTICE + job.description
        job.meta_description = job.meta_description.replace(
            TEST_DATA_MARKER, DEMO_MARKER
        )
        job.meta_title = f"{job.title} Jobs - {company.name}"
        job.company_name = company.name
        job.company_description = company.profile
        job.slug = job.public_slug()
        job.save()
