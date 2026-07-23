"""Email notification sent when an upload run finishes.

Recipient and SMTP overrides are configured through the Config page and
persisted via store; any override left blank falls back to the settings.py
default.
"""
import smtplib
from email.mime.text import MIMEText

import settings
import store


def _smtp_config():
    return (
        store.get("smtp_server") or settings.SMTP_SERVER,
        int(store.get("smtp_port") or settings.SMTP_PORT),
        store.get("smtp_user") or settings.SMTP_USER,
        store.get("smtp_pass") or settings.SMTP_PASS,
    )


def send_upload_summary(message):
    """Email the given summary to the configured recipient, if any. Best
    effort: failures are logged, never raised, so a broken mail config can't
    break the upload run itself."""
    recipient = store.get("notify_email")
    if not recipient:
        return

    server, port, user, password = _smtp_config()
    msg = MIMEText(message)
    msg["Subject"] = "Cloud Upload finished"
    msg["From"] = user
    msg["To"] = recipient

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(user, [recipient], msg.as_string())
    except Exception as exc:
        print(f"Email notification failed: {exc}")
