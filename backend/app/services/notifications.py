from __future__ import annotations

import json
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal

import httpx

from app.core.config import settings


Channel = Literal["email", "sms"]


@dataclass
class EmailAttachment:
    filename: str
    media_type: str
    content: str
    method: str | None = None  # iTIP method (REQUEST, CANCEL) when applicable


@dataclass
class DeliveryResult:
    status: str
    detail: str | None = None


def send_notification(
    *,
    channel: Channel,
    target: str,
    subject: str,
    body: str,
    metadata: dict[str, object] | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> DeliveryResult:
    if channel == "sms":
        if settings.sms_mode.lower() == "twilio":
            return _send_sms_via_twilio(target=target, body=body)
        return _write_outbox(
            channel=channel,
            target=target,
            subject=subject,
            body=body,
            metadata=metadata,
            attachments=None,
        )

    mode = settings.notification_mode.lower()
    if mode == "smtp":
        return _send_email_via_smtp(
            target=target,
            subject=subject,
            body=body,
            attachments=attachments,
        )
    return _write_outbox(
        channel=channel,
        target=target,
        subject=subject,
        body=body,
        metadata=metadata,
        attachments=attachments,
    )


def build_twilio_payload(
    *, account_sid: str, auth_token: str, from_number: str, to: str, body: str
) -> tuple[str, dict[str, str], tuple[str, str]]:
    """URL, form data, and basic-auth tuple for a Twilio Messages request."""
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {"From": from_number, "To": to, "Body": body}
    auth = (account_sid, auth_token)
    return url, data, auth


def _send_sms_via_twilio(*, target: str, body: str) -> DeliveryResult:
    if not (
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_from_number
    ):
        return DeliveryResult(status="failed", detail="twilio_not_configured")

    url, data, auth = build_twilio_payload(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        from_number=settings.twilio_from_number,
        to=target,
        body=body,
    )
    try:
        response = httpx.post(url, data=data, auth=auth, timeout=10.0)
    except Exception as exc:  # pragma: no cover - integration path
        return DeliveryResult(status="failed", detail=str(exc))

    if response.status_code >= 400:
        return DeliveryResult(status="failed", detail=f"twilio_http_{response.status_code}")
    return DeliveryResult(status="sent")


def _send_email_via_smtp(
    *,
    target: str,
    subject: str,
    body: str,
    attachments: list[EmailAttachment] | None = None,
) -> DeliveryResult:
    if not settings.smtp_host:
        return DeliveryResult(status="failed", detail="smtp_host_not_configured")

    message = EmailMessage()
    message["From"] = settings.notification_from_email
    message["To"] = target
    message["Subject"] = subject
    message.set_content(body)

    for attachment in attachments or []:
        major, _, minor = attachment.media_type.partition("/")
        message.add_attachment(
            attachment.content.encode("utf-8"),
            maintype=major or "application",
            subtype=minor or "octet-stream",
            filename=attachment.filename,
        )

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
                _login_and_send(server, message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                _login_and_send(server, message)
    except Exception as exc:  # pragma: no cover - integration path
        return DeliveryResult(status="failed", detail=str(exc))

    return DeliveryResult(status="sent")


def _login_and_send(server: smtplib.SMTP, message: EmailMessage) -> None:
    if settings.smtp_username and settings.smtp_password:
        server.login(settings.smtp_username, settings.smtp_password)
    server.send_message(message)


def _write_outbox(
    *,
    channel: str,
    target: str,
    subject: str,
    body: str,
    metadata: dict[str, object] | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> DeliveryResult:
    outbox_dir = Path(settings.notification_outbox_dir)
    if not outbox_dir.is_absolute():
        outbox_dir = Path.cwd() / outbox_dir
    outbox_dir.mkdir(parents=True, exist_ok=True)

    safe_target = "".join(ch if ch.isalnum() else "_" for ch in target)[:60] or "unknown"
    safe_subject = "".join(ch if ch.isalnum() else "_" for ch in subject)[:32] or "unknown"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    filename = outbox_dir / f"{channel}_{safe_target}_{safe_subject}_{stamp}.json"
    payload = {
        "channel": channel,
        "target": target,
        "subject": subject,
        "body": body,
        "metadata": metadata or {},
        "attachments": [
            {
                "filename": attachment.filename,
                "media_type": attachment.media_type,
                "content": attachment.content,
                "method": attachment.method,
            }
            for attachment in (attachments or [])
        ],
    }
    filename.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return DeliveryResult(status="sent", detail=str(filename))
