"""
Contact-form emailing.

This used to be a second, separate Flask process (app.py) that the old
README never actually told anyone to start. It's now just another FastAPI
route/service in the same process -- one backend, one port, one thing to run.
"""
from __future__ import annotations

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend import config
from backend.utils.errors import AppError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send_contact_email(*, name: str, email: str, message: str) -> None:
    name, email, message = name.strip(), email.strip(), message.strip()
    if not name or not email or not message:
        raise AppError(400, "MISSING_FIELDS", "Name, email, and message are all required.")
    if not _EMAIL_RE.match(email):
        raise AppError(400, "INVALID_EMAIL", "That doesn't look like a valid email address.")

    if not (config.SMTP_USERNAME and config.SMTP_PASSWORD and config.RECEIVER_EMAIL):
        raise AppError(
            503,
            "CONTACT_NOT_CONFIGURED",
            "The contact form isn't configured on this server yet "
            "(SMTP_USERNAME / SMTP_PASSWORD / RECEIVER_EMAIL are not set).",
        )

    body = MIMEMultipart()
    body["From"] = config.SMTP_USERNAME
    body["To"] = config.RECEIVER_EMAIL
    body["Subject"] = f"DocQuery contact form: {name}"
    body.attach(MIMEText(f"From: {name} <{email}>\n\n{message}", "plain"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(body)
    except smtplib.SMTPException as exc:
        raise AppError(502, "EMAIL_SEND_FAILED", "The message couldn't be sent right now.") from exc
