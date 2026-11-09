import json

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    args = "<filename>"
    help = "Loads the initial data in to database"

    def handle(self, *args, **options):
        # GradBridge serves Singapore and Australia: locations, qualifications and
        # languages come from its own commands instead of the upstream Indian
        # fixtures (countries/states/cities.json, qualification.json, languages.json).
        call_command("load_gradbridge_locations", stdout=self.stdout)
        call_command("loaddata", "peeldb/fixtures/skills.json", verbosity=0)
        call_command("loaddata", "peeldb/fixtures/industries.json", verbosity=0)
        call_command("load_gradbridge_reference_data", stdout=self.stdout)
        call_command("loaddata", "peeldb/fixtures/functionalarea.json", verbosity=0)
        self.stdout.write(self.style.SUCCESS("Successfully loaded initial data"))

        result = {"message": "Successfully loaded initial data"}
        return json.dumps(result)
