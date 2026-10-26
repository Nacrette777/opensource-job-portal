"""
GradBridge: load the qualification and language choices for Singapore and Australia.

The upstream fixtures (qualification.json, languages.json) are Indian: B.Tech, MCA,
"10th pass", ITI; Telugu, Hindi. GradBridge ships its own lists instead: the
Australian Qualifications Framework levels and Singapore's school, ITE and
polytechnic qualifications, and languages widely spoken in both countries. Like
load_gradbridge_locations, the command is idempotent: rows are matched by name
(qualifications also by slug), only created or re-activated, never deleted.

    python manage.py load_gradbridge_reference_data
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from peeldb.models import Language, Qualification

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
    help = "Create or re-activate GradBridge's qualification and language choices (Singapore, Australia)."

    def handle(self, *args, **options):
        created = {"qualifications": 0, "languages": 0}
        with transaction.atomic():
            for name in QUALIFICATIONS:
                qualification = Qualification.objects.filter(slug=slugify(name)).first()
                if qualification is None:
                    qualification = Qualification.objects.filter(name__iexact=name).first()
                if qualification is None:
                    Qualification.objects.create(name=name, slug=slugify(name), status="Active")
                    created["qualifications"] += 1
                elif qualification.status != "Active":
                    qualification.status = "Active"
                    qualification.save(update_fields=["status"])
            for name in LANGUAGES:
                if not Language.objects.filter(name__iexact=name).exists():
                    Language.objects.create(name=name)
                    created["languages"] += 1

        self.stdout.write(
            f"Qualifications: {len(QUALIFICATIONS)} (created {created['qualifications']}); "
            f"languages: {len(LANGUAGES)} (created {created['languages']})."
        )
