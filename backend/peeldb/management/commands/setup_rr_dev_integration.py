"""
GradBridge: register this site as an OAuth client of Reactive Resume and
generate the token-encryption key.

RR allows dynamic client registration (RFC 7591). The client secret and
Fernet key are written to --output as environment variables for the Django
process; nothing secret is printed. Run it once per environment: with
DEBUG on for local development, or with --allow-production when setting up a
deployment (then store the values in the platform's secret store).
"""

import json
from pathlib import Path

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Register a local RR OAuth client and write RR_* settings to a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            help="JSON file to create (refuses to overwrite). Keep it out of Git.",
        )
        parser.add_argument(
            "--client-name", default="GradBridge PeelJobs (local development)"
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Run with DEBUG off, to register a deployment's fixed client.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["allow_production"]:
            raise CommandError(
                "DEBUG is off. To register a deployment's client deliberately, pass --allow-production."
            )

        output = Path(options["output"])
        if output.exists():
            raise CommandError(f"{output} already exists; refusing to overwrite it.")
        if not output.parent.is_dir():
            raise CommandError(f"Directory {output.parent} does not exist.")

        redirect_uri = settings.RR_OAUTH_REDIRECT_URI
        try:
            response = requests.post(
                f"{settings.RR_INTERNAL_URL}/api/auth/oauth2/register",
                json={
                    "client_name": options["client_name"],
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post",
                    "scope": "openid profile email offline_access",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            raise CommandError(
                f"Could not reach RR at {settings.RR_INTERNAL_URL}: {exc}"
            ) from exc

        body = response.json() if response.content else {}
        if response.status_code not in (200, 201) or not body.get("client_secret"):
            raise CommandError(
                f"RR refused the registration ({response.status_code}): {body.get('error_description') or body.get('error') or 'no details'}"
            )

        values = {
            "RR_BASE_URL": settings.RR_BASE_URL,
            "RR_OAUTH_CLIENT_ID": body["client_id"],
            "RR_OAUTH_CLIENT_SECRET": body["client_secret"],
            "RR_OAUTH_REDIRECT_URI": redirect_uri,
            "RR_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
        with output.open("x", encoding="utf-8") as fh:
            json.dump(values, fh, indent=2)

        self.stdout.write(
            self.style.SUCCESS(
                f"Registered RR client {body['client_id']} for {redirect_uri}; settings written to {output}"
            )
        )
