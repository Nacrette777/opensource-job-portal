"""
GradBridge: load the education and language choices for Singapore and Australia.

The upstream fixtures (qualification.json, languages.json) are Indian: B.Tech, MCA,
"10th pass", ITI; Telugu, Hindi. GradBridge ships its own lists instead: the
Australian Qualifications Framework levels and Singapore's school, ITE and
polytechnic qualifications; the degrees (qualification + field of study) that the
profile's education form offers once a qualification is chosen; universities,
polytechnics and TAFEs in both countries (students can still type an institute
that is not listed); and languages widely spoken in both countries. Like
load_gradbridge_locations, the command is idempotent: rows are matched by name
(qualifications also by slug), only created or re-activated, never deleted.
Institutes are placed in their city when load_gradbridge_locations has run.

    python manage.py load_gradbridge_reference_data
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from peeldb.models import City, Degree, EducationInstitue, Language, Qualification

from .test_data.sg_au_names import COLLEGES, UNIVERSITIES

QUALIFICATIONS = [
    # Secondary
    "GCE O-Level",
    "GCE A-Level",
    "IB Diploma",
    "Year 12 Certificate (HSC/VCE/QCE/WACE/SACE)",
    # Vocational (ITE in Singapore, VET/TAFE in Australia)
    "Nitec",
    "Higher Nitec",
    "Certificate III",
    "Certificate IV",
    # Diplomas
    "Diploma",
    "Polytechnic Diploma",
    "Advanced Diploma",
    "Associate Degree",
    # Higher education
    "Bachelor's Degree",
    "Bachelor's Degree (Honours)",
    "Graduate Certificate",
    "Graduate Diploma",
    "Master's Degree",
    "MBA",
    "Doctoral Degree (PhD)",
]

# Fields of study offered for each qualification (a Degree row is one pair).
_SECONDARY = ["General"]
_VOCATIONAL = [
    "Information Technology",
    "Business",
    "Accounting",
    "Engineering Services",
    "Hospitality",
    "Health Services",
]
_DIPLOMA = [
    "Information Technology",
    "Business",
    "Accounting",
    "Engineering",
    "Design",
    "Nursing",
]
_HIGHER = [
    "Computer Science",
    "Information Technology",
    "Software Engineering",
    "Data Science",
    "Cyber Security",
    "Electrical Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Business",
    "Commerce",
    "Accounting",
    "Finance",
    "Economics",
    "Marketing",
    "Psychology",
    "Nursing",
    "Education",
    "Law",
    "Design",
    "Science",
]
FIELDS_OF_STUDY = {
    "GCE O-Level": _SECONDARY,
    "GCE A-Level": _SECONDARY,
    "IB Diploma": _SECONDARY,
    "Year 12 Certificate (HSC/VCE/QCE/WACE/SACE)": _SECONDARY,
    "Nitec": _VOCATIONAL,
    "Higher Nitec": _VOCATIONAL,
    "Certificate III": _VOCATIONAL,
    "Certificate IV": _VOCATIONAL,
    "Diploma": _DIPLOMA,
    "Polytechnic Diploma": _DIPLOMA,
    "Advanced Diploma": _DIPLOMA,
    "Associate Degree": _DIPLOMA,
    "Bachelor's Degree": _HIGHER,
    "Bachelor's Degree (Honours)": _HIGHER,
    "Graduate Certificate": _HIGHER,
    "Graduate Diploma": _HIGHER,
    "Master's Degree": _HIGHER,
    "MBA": ["Business Administration"],
    "Doctoral Degree (PhD)": _HIGHER,
}

LANGUAGES = [
    "English",
    "Mandarin",
    "Malay",
    "Tamil",
    "Cantonese",
    "Hokkien",
    "Vietnamese",
    "Arabic",
    "Hindi",
    "Punjabi",
    "Greek",
    "Italian",
    "Indonesian",
    "Japanese",
    "Korean",
]


class Command(BaseCommand):
    help = "Create or re-activate GradBridge's education and language choices (Singapore, Australia)."

    def handle(self, *args, **options):
        created = {"qualifications": 0, "degrees": 0, "institutes": 0, "languages": 0}
        with transaction.atomic():
            qualifications = {}
            for name in QUALIFICATIONS:
                qualification = Qualification.objects.filter(slug=slugify(name)).first()
                if qualification is None:
                    qualification = Qualification.objects.filter(
                        name__iexact=name
                    ).first()
                if qualification is None:
                    qualification = Qualification.objects.create(
                        name=name, slug=slugify(name), status="Active"
                    )
                    created["qualifications"] += 1
                elif qualification.status != "Active":
                    qualification.status = "Active"
                    qualification.save(update_fields=["status"])
                qualifications[name] = qualification

            for name, fields in FIELDS_OF_STUDY.items():
                for field in fields:
                    _, made = Degree.objects.get_or_create(
                        degree_name=qualifications[name],
                        specialization=field,
                        defaults={"degree_type": "Permanent"},
                    )
                    created["degrees"] += made

            cities = {city.slug: city for city in City.objects.select_related("state")}
            for name, city_slug in UNIVERSITIES + COLLEGES:
                if EducationInstitue.objects.filter(name__iexact=name).exists():
                    continue
                city = cities.get(city_slug)
                EducationInstitue.objects.create(
                    name=name,
                    city=city,
                    address=f"{city.name}, {city.state.name}" if city else "",
                )
                created["institutes"] += 1

            for name in LANGUAGES:
                if not Language.objects.filter(name__iexact=name).exists():
                    Language.objects.create(name=name)
                    created["languages"] += 1

        degree_count = sum(len(fields) for fields in FIELDS_OF_STUDY.values())
        self.stdout.write(
            f"Qualifications: {len(QUALIFICATIONS)} (created {created['qualifications']}); "
            f"degrees: {degree_count} (created {created['degrees']}); "
            f"institutes: {len(UNIVERSITIES) + len(COLLEGES)} (created {created['institutes']}); "
            f"languages: {len(LANGUAGES)} (created {created['languages']})."
        )
