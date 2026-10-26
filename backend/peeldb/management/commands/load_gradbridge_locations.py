"""
GradBridge: load the location choices the profile form offers (country → state → city).

The upstream fixtures (countries/states/cities.json) are India-centric samples with
placeholder rows, so GradBridge ships its own list: Australia's eight states and
territories (as the ABS lists them) and their capital and major cities. The command
is idempotent: rows are matched by slug and only created or re-enabled, never
deleted, so it can be re-run after the list below changes.

    python manage.py load_gradbridge_locations
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from peeldb.models import City, Country, State

AUSTRALIA = {
    "New South Wales": ["Sydney", "Newcastle", "Wollongong", "Central Coast"],
    "Victoria": ["Melbourne", "Geelong", "Ballarat", "Bendigo"],
    "Queensland": ["Brisbane", "Gold Coast", "Sunshine Coast", "Townsville", "Cairns"],
    "South Australia": ["Adelaide"],
    "Western Australia": ["Perth"],
    "Tasmania": ["Hobart", "Launceston"],
    "Northern Territory": ["Darwin", "Alice Springs"],
    "Australian Capital Territory": ["Canberra"],
}


class Command(BaseCommand):
    help = "Create or re-enable GradBridge's country/state/city choices (Australia)."

    def handle(self, *args, **options):
        created = {"country": 0, "state": 0, "city": 0}
        with transaction.atomic():
            country, made = Country.objects.get_or_create(
                slug="australia", defaults={"name": "Australia", "status": "Enabled"}
            )
            created["country"] += made
            self._enable(country)
            for state_name, cities in AUSTRALIA.items():
                state, made = State.objects.get_or_create(
                    country=country,
                    slug=slugify(state_name),
                    defaults={"name": state_name, "status": "Enabled"},
                )
                created["state"] += made
                self._enable(state)
                for city_name in cities:
                    city = City.objects.filter(state=state, slug=slugify(city_name)).first()
                    if not city:
                        City(name=city_name, slug=slugify(city_name), state=state, status="Enabled").save()
                        created["city"] += 1
                    else:
                        self._enable(city)

        total_cities = City.objects.filter(state__country=country).count()
        self.stdout.write(
            f"Australia: {State.objects.filter(country=country).count()} states/territories, "
            f"{total_cities} cities (created {created['country']} country, "
            f"{created['state']} states, {created['city']} cities)."
        )

    @staticmethod
    def _enable(obj):
        if obj.status != "Enabled":
            obj.status = "Enabled"
            obj.save(update_fields=["status"])
