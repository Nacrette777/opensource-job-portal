"""The Azure Communication Services email backend (jobsp/acs_email.py)."""

import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.test import SimpleTestCase, override_settings

from jobsp.acs_email import parse_connection_string, signed_headers

KEY = base64.b64encode(b"not-a-real-key").decode()
CONNECTION = f"endpoint=https://gb-test.communication.azure.com/;accesskey={KEY}"
ACS = override_settings(
    EMAIL_BACKEND="jobsp.acs_email.EmailBackend",
    ACS_EMAIL_CONNECTION_STRING=CONNECTION,
    DEFAULT_FROM_EMAIL="DoNotReply@example.azurecomm.net",
)


def accepted():
    return MagicMock(status_code=202, headers={"operation-location": "op"}, text="")


class ConnectionStringTests(SimpleTestCase):
    def test_parses_endpoint_and_key(self):
        endpoint, key = parse_connection_string(CONNECTION)
        self.assertEqual(endpoint, "https://gb-test.communication.azure.com")
        self.assertEqual(key, KEY)

    def test_missing_parts_are_a_configuration_error(self):
        for value in (
            "",
            "endpoint=https://x.communication.azure.com/",
            "accesskey=abc",
        ):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                parse_connection_string(value)


class SignatureTests(SimpleTestCase):
    def test_signs_method_path_date_host_and_body_hash(self):
        url = (
            "https://gb-test.communication.azure.com/emails:send?api-version=2023-03-31"
        )
        body = b'{"a":1}'
        date = "Sun, 08 Nov 2026 10:00:00 GMT"
        headers = signed_headers("POST", url, body, KEY, date=date)

        content_hash = base64.b64encode(hashlib.sha256(body).digest()).decode()
        expected = base64.b64encode(
            hmac.new(
                base64.b64decode(KEY),
                (
                    "POST\n/emails:send?api-version=2023-03-31\n"
                    f"{date};gb-test.communication.azure.com;{content_hash}"
                ).encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        self.assertEqual(headers["x-ms-date"], date)
        self.assertEqual(headers["x-ms-content-sha256"], content_hash)
        self.assertEqual(
            headers["Authorization"],
            "HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256"
            f"&Signature={expected}",
        )


@ACS
class BackendTests(SimpleTestCase):
    @patch("jobsp.acs_email.requests.post", return_value=accepted())
    def test_html_message_with_reply_to(self, post):
        message = EmailMessage(
            "Verify your email | GradBridge",
            "<p>Hello</p>",
            "GradBridge <DoNotReply@example.azurecomm.net>",
            ["Student A <a@example.test>"],
            reply_to=["help@example.test"],
        )
        message.content_subtype = "html"
        self.assertEqual(message.send(), 1)

        url = post.call_args.args[0]
        self.assertEqual(
            url,
            "https://gb-test.communication.azure.com/emails:send?api-version=2023-03-31",
        )
        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["senderAddress"], "DoNotReply@example.azurecomm.net")
        self.assertEqual(
            payload["recipients"]["to"],
            [{"address": "a@example.test", "displayName": "Student A"}],
        )
        self.assertEqual(
            payload["content"],
            {"subject": "Verify your email | GradBridge", "html": "<p>Hello</p>"},
        )
        self.assertEqual(payload["replyTo"], [{"address": "help@example.test"}])
        self.assertTrue(payload["userEngagementTrackingDisabled"])
        self.assertTrue(
            post.call_args.kwargs["headers"]["Authorization"].startswith("HMAC-SHA256 ")
        )

    @patch("jobsp.acs_email.requests.post", return_value=accepted())
    def test_plain_text_with_html_alternative_and_attachment(self, post):
        message = EmailMultiAlternatives("Hi", "plain", to=["a@example.test"])
        message.attach_alternative("<b>rich</b>", "text/html")
        message.attach("notes.txt", "hello", "text/plain")
        message.send()

        payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(payload["content"]["plainText"], "plain")
        self.assertEqual(payload["content"]["html"], "<b>rich</b>")
        self.assertEqual(payload["senderAddress"], "DoNotReply@example.azurecomm.net")
        self.assertEqual(
            payload["attachments"],
            [
                {
                    "name": "notes.txt",
                    "contentType": "text/plain",
                    "contentInBase64": base64.b64encode(b"hello").decode(),
                }
            ],
        )

    @patch("jobsp.acs_email.requests.post")
    def test_rejection_raises_unless_fail_silently(self, post):
        post.return_value = MagicMock(status_code=400, text='{"error":"bad sender"}')
        with self.assertRaisesMessage(RuntimeError, "bad sender"):
            send_mail("Hi", "body", None, ["a@example.test"])
        self.assertEqual(
            send_mail("Hi", "body", None, ["a@example.test"], fail_silently=True), 0
        )

    @patch("jobsp.acs_email.requests.post")
    def test_message_without_recipients_is_skipped(self, post):
        self.assertEqual(EmailMessage("Hi", "body", to=[]).send(), 0)
        post.assert_not_called()
