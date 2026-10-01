from collections.abc import Sequence
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend


class SesEmailBackend(BaseEmailBackend):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.client = boto3.client(
            "ses",
            region_name=settings.AWS_DEFAULT_REGION,
            endpoint_url=getattr(settings, "AWS_SES_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0

        sent_messages = 0
        for message in email_messages:
            recipients = message.recipients()
            if not recipients:
                continue

            body: dict[str, dict[str, str]] = {"Text": {"Data": str(message.body or "")}}
            for alternative, mimetype in getattr(message, "alternatives", []):
                if mimetype == "text/html":
                    body["Html"] = {"Data": str(alternative)}
                    break

            payload: dict[str, Any] = {
                "Source": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "Destination": {
                    "ToAddresses": message.to or [],
                    "CcAddresses": message.cc or [],
                    "BccAddresses": message.bcc or [],
                },
                "Message": {
                    "Subject": {"Data": message.subject or ""},
                    "Body": body,
                },
            }
            if message.reply_to:
                payload["ReplyToAddresses"] = message.reply_to

            try:
                self.client.send_email(**payload)
                sent_messages += 1
            except (BotoCoreError, ClientError):
                if not self.fail_silently:
                    raise

        return sent_messages
