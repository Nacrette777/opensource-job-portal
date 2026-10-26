"""S3-04: GradBridge location choices, and how location and phone reach exports."""

import io

from django.core.management import call_command
from django.test import TestCase

from peeldb.management.commands.load_gradbridge_locations import AUSTRALIA
from peeldb.models import City, Country, State, User
from peeldb.resume_export import build_json_resume


def load():
    out = io.StringIO()
    call_command("load_gradbridge_locations", stdout=out)
    return out.getvalue()


class LoadLocationsTests(TestCase):
    def test_loads_the_australian_states_and_cities(self):
        load()

        country = Country.objects.get(slug="australia")
        self.assertEqual(
            sorted(State.objects.filter(country=country).values_list("name", flat=True)),
            sorted(AUSTRALIA),
        )
        darwin = City.objects.get(slug="darwin")
        self.assertEqual(darwin.state.name, "Northern Territory")
        self.assertEqual(darwin.status, "Enabled")
        self.assertEqual(
            City.objects.filter(state__country=country).count(),
            sum(len(cities) for cities in AUSTRALIA.values()),
        )

    def test_loads_singapore_as_one_city_state(self):
        load()

        singapore = City.objects.get(slug="singapore")
        self.assertEqual(singapore.state.name, "Singapore")
        self.assertEqual(singapore.state.country.name, "Singapore")
        self.assertEqual(singapore.status, "Enabled")

    def test_running_again_creates_nothing_new(self):
        load()
        counts = (Country.objects.count(), State.objects.count(), City.objects.count())

        output = load()

        self.assertEqual((Country.objects.count(), State.objects.count(), City.objects.count()), counts)
        self.assertEqual(output.count("created 0 country, 0 states, 0 cities"), 2)

    def test_reuses_existing_rows_by_slug_and_re_enables_them(self):
        country = Country.objects.create(name="Australia", slug="australia", status="Disabled")
        state = State.objects.create(country=country, name="South Australia", slug="south-australia")
        City.objects.create(state=state, name="Adelaide", slug="adelaide", status="Disabled")

        load()

        self.assertEqual(Country.objects.filter(slug="australia").count(), 1)
        self.assertEqual(State.objects.filter(slug="south-australia").count(), 1)
        self.assertEqual(City.objects.get(slug="adelaide").status, "Enabled")
        self.assertEqual(Country.objects.get(slug="australia").status, "Enabled")

    def test_never_deletes_other_locations(self):
        other = Country.objects.create(name="Elsewhere", slug="elsewhere")

        load()

        self.assertTrue(Country.objects.filter(pk=other.pk).exists())


class LocationExportTests(TestCase):
    def setUp(self):
        load()
        self.user = User.objects.create(
            username="loc-student",
            email="loc.student@example.com",
            user_type="JS",
            first_name="Loc",
            last_name="Student",
            mobile="0412 000 123",
            alternate_mobile="0499000111",
            address="1 Synthetic Street",
            pincode="0800",
            current_city=City.objects.get(slug="darwin"),
        )

    def test_location_maps_city_region_and_postcode_without_inventing_a_country_code(self):
        export = build_json_resume(self.user)

        location = export.data["basics"]["location"]
        self.assertEqual(location["city"], "Darwin")
        self.assertEqual(location["region"], "Northern Territory")
        self.assertEqual(location["postalCode"], "0800")
        self.assertNotIn("countryCode", location)
        self.assertTrue(any("countryCode" in w for w in export.warnings))

    def test_only_the_main_mobile_is_exported(self):
        export = build_json_resume(self.user)

        self.assertEqual(export.data["basics"]["phone"], "0412 000 123")
        self.assertNotIn("0499000111", repr(export.data))
