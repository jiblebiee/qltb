from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import TypedDict
from zoneinfo import ZoneInfo

from ..config import settings
from ..db import SessionLocal

logger = logging.getLogger(__name__)
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class EmailAttachment(TypedDict, total=False):
    filename: str
    content: bytes
    mime_type: str
    subtype: str


def email_is_enabled() -> bool:
    return bool(settings.smtp_enabled and settings.smtp_host and settings.mail_from)


def default_alert_recipients() -> list[str]:
    raw = settings.mail_alert_recipients or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def send_email(
    subject: str,
    body: str,
    recipients: list[str],
    html_body: str | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> bool:
    clean_recipients = [item.strip() for item in recipients if item and item.strip()]
    if not clean_recipients:
        logger.info("Skip email: no recipients")
        _log_email_event(subject, clean_recipients, html_body or body, status="SKIPPED", error_message="No recipients")
        return False

    if not email_is_enabled():
        logger.warning("Skip email: SMTP is not configured")
        _log_email_event(subject, clean_recipients, html_body or body, status="SKIPPED", error_message="SMTP is not configured")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.mail_from
    message["To"] = ", ".join(clean_recipients)
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    for attachment in attachments or []:
        payload = attachment.get("content") or b""
        filename = attachment.get("filename") or "attachment.bin"
        mime_type = attachment.get("mime_type") or "application/octet-stream"
        maintype, _, subtype = mime_type.partition("/")
        message.add_attachment(payload, maintype=maintype or "application", subtype=subtype or attachment.get("subtype") or "octet-stream", filename=filename)

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                _login_if_needed(server)
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                _login_if_needed(server)
                server.send_message(message)
        _log_email_event(subject, clean_recipients, html_body or body, status="DONE")
        return True
    except Exception as exc:
        logger.exception("Failed to send email alert")
        _log_email_event(subject, clean_recipients, html_body or body, status="FAILED", error_message=str(exc))
        return False


def _login_if_needed(server: smtplib.SMTP) -> None:
    if not settings.smtp_username:
        return
    if not server.has_extn("auth"):
        logger.warning("Skip SMTP login: server does not advertise AUTH")
        return
    server.login(settings.smtp_username, settings.smtp_password or "")


def _log_email_event(
    subject: str,
    recipients: list[str],
    body: str,
    status: str,
    error_message: str | None = None,
) -> None:
    try:
        from .. import models

        preview = (body or "").strip()

        with SessionLocal() as db:
            db.add(
                models.EmailLog(
                    subject=subject[:255],
                    recipients=", ".join(recipients),
                    body_preview=preview or None,
                    status=status,
                    error_message=error_message,
                    created_at=_now_local_naive(),
                )
            )
            db.commit()
    except Exception:
        logger.exception("Failed to persist email log")


def _now_local_naive() -> datetime:
    return datetime.now(BANGKOK_TZ).replace(tzinfo=None)
