"""
Django email backend for Azure Communication Services (ACS) Email.

It calls the ACS REST API ("emails:send") with the resource's connection
string, signed with HMAC-SHA256 as ACS requires. That needs neither the Azure
SDK (only `requests`, already a dependency) nor an Entra app registration,
which ACS SMTP would. Configure it in settings_gradbridge:

    EMAIL_BACKEND = "jobsp.acs_email.EmailBackend"
    ACS_EMAIL_CONNECTION_STRING = "endpoint=https://<name>.communication.azure.com/;accesskey=<key>"
    DEFAULT_FROM_EMAIL = "DoNotReply@<domain>.azurecomm.net"

ACS accepts the message (202) and delivers it asynchronously; delivery
failures show in the resource's logs, not here.
"""

import base64
import hashlib
import hmac
import json
import logging
import mimetypes
from email.utils import formatdate, parseaddr
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

API_VERSION = "2023-03-31"


def parse_connection_string(value):
    parts = dict(item.split("=", 1) for item in (value or "").split(";") if "=" in item)
    parts = {key.strip().lower(): val.strip() for key, val in parts.items()}
    if not parts.get("endpoint") or not parts.get("accesskey"):
        raise ImproperlyConfigured(
            "ACS_EMAIL_CONNECTION_STRING must contain endpoint= and accesskey="
        )
    return parts["endpoint"].rstrip("/"), parts["accesskey"]


def signed_headers(method, url, body, access_key, date=None):
    """The x-ms-date, x-ms-content-sha256 and Authorization headers ACS checks."""
    parsed = urlsplit(url)
    path_and_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    date = date or formatdate(usegmt=True)
    content_hash = base64.b64encode(hashlib.sha256(body).digest()).decode()
    to_sign = f"{method}\n{path_and_query}\n{date};{parsed.netloc};{content_hash}"
    signature = base64.b64encode(
        hmac.new(
            base64.b64decode(access_key), to_sign.encode(), hashlib.sha256
        ).digest()
    ).decode()
    return {
        "x-ms-date": date,
        "x-ms-content-sha256": content_hash,
        "Authorization": (
            "HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256"
            f"&Signature={signature}"
        ),
    }


def _addresses(values):
    result = []
    for value in values or []:
        name, address = parseaddr(value)
        if address:
            result.append(
                {"address": address, **({"displayName": name} if name else {})}
            )
    return result


def message_payload(message):
    """ACS JSON for a Django EmailMessage (or EmailMultiAlternatives)."""
    content = {"subject": message.subject}
    if message.content_subtype == "html":
        content["html"] = message.body
    else:
        content["plainText"] = message.body
    for alternative in getattr(message, "alternatives", []) or []:
        alt_content, mimetype = alternative[0], alternative[1]
        if mimetype == "text/html":
            content["html"] = alt_content

    payload = {
        # ACS takes only the address; the display name belongs to the sender
        # username configured on the domain.
        "senderAddress": parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)[
            1
        ],
        "recipients": {
            "to": _addresses(message.to),
            "cc": _addresses(message.cc),
            "bcc": _addresses(message.bcc),
        },
        "content": content,
        "userEngagementTrackingDisabled": True,
    }
    if message.reply_to:
        payload["replyTo"] = _addresses(message.reply_to)

    attachments = []
    for attachment in message.attachments:
        if not isinstance(attachment, tuple) and hasattr(attachment, "get_payload"):
            name = attachment.get_filename() or "attachment"
            data = attachment.get_payload(decode=True) or b""
            mimetype = attachment.get_content_type()
        else:
            name, data, mimetype = attachment[0], attachment[1], attachment[2]
            if isinstance(data, str):
                data = data.encode()
        attachments.append(
            {
                "name": name,
                "contentType": mimetype
                or mimetypes.guess_type(name)[0]
                or "application/octet-stream",
                "contentInBase64": base64.b64encode(data).decode(),
            }
        )
    if attachments:
        payload["attachments"] = attachments
    return payload


class EmailBackend(BaseEmailBackend):
    timeout = 20

    def __init__(self, fail_silently=False, connection_string=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.endpoint, self.access_key = parse_connection_string(
            connection_string or getattr(settings, "ACS_EMAIL_CONNECTION_STRING", "")
        )

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                self._send(message)
            except Exception:
                if not self.fail_silently:
                    raise
                logger.exception("ACS email send failed")
            else:
                sent += 1
        return sent

    def _send(self, message):
        url = f"{self.endpoint}/emails:send?api-version={API_VERSION}"
        body = json.dumps(message_payload(message)).encode()
        headers = {
            "Content-Type": "application/json",
            **signed_headers("POST", url, body, self.access_key),
        }
        response = requests.post(url, data=body, headers=headers, timeout=self.timeout)
        if response.status_code != 202:
            # The body names the problem (e.g. an unverified sender) and holds
            # no secret; the request headers, which do, are not logged.
            raise RuntimeError(
                f"ACS email send returned {response.status_code}: {response.text[:500]}"
            )
        logger.info(
            "ACS accepted email, operation %s",
            response.headers.get("operation-location", ""),
        )
