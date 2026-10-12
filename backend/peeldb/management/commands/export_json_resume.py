"""Export one explicitly selected test student; no writes to either database."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from peeldb.models import User
from peeldb.resume_export import build_json_resume


class Command(BaseCommand):
    help = "Export one explicitly selected job seeker as standard JSON Resume."

    def add_arguments(self, parser):
        student = parser.add_mutually_exclusive_group(required=True)
        student.add_argument("--user-id", type=int, help="Exact test student's User ID")
        student.add_argument(
            "--email", help="Exact test student's email (case insensitive)"
        )
        parser.add_argument(
            "--output", type=Path, required=True, help="New UTF-8 JSON file"
        )

    def handle(self, *args, **options):
        if (options.get("user_id") is None) == (options.get("email") is None):
            raise CommandError("Specify exactly one of --user-id or --email.")
        lookup = (
            {"pk": options["user_id"]}
            if options.get("user_id") is not None
            else {"email__iexact": options["email"].strip()}
        )
        try:
            user = User.objects.select_related(
                "current_city__state__country",
                "city__state__country",
                "state__country",
                "country",
            ).get(**lookup)
        except User.DoesNotExist as error:
            raise CommandError(
                "Specified student does not exist; nothing exported."
            ) from error
        except User.MultipleObjectsReturned as error:
            raise CommandError(
                "Email is ambiguous; specify --user-id instead."
            ) from error

        try:
            result = build_json_resume(user)
        except ValueError as error:
            raise CommandError(str(error)) from error

        output = Path(options["output"])
        payload = json.dumps(result.data, ensure_ascii=False, indent=2) + "\n"
        try:
            # Never overwrite an existing file (including a linked destination).
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
        except OSError as error:
            raise CommandError(
                "Cannot create output file; use an existing directory and a new filename."
            ) from error

        for warning in result.warnings:
            self.stderr.write(f"WARNING: {warning}")
        counts = ", ".join(
            f"{section}={len(result.data.get(section, []))}"
            for section in ("education", "work", "skills", "projects")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Exported standard JSON Resume ({counts}).")
        )
