"""Email notification sent when an upload run finishes.

Sent to the email address the Google Drive account is bound to, using the
SMTP_* settings in settings.py, when enabled via the "Automatically send
email when upload is finished" switch on the Config page.
"""
import smtplib
from email.mime.text import MIMEText

import settings
import store
import gdrive


def send_upload_summary(message):
    """Email the given summary to the Drive account's address. Best effort:
    failures are logged, never raised, so a broken mail config can't break
    the upload run itself."""
    if not store.get("notify_on_upload"):
        return

    recipient = gdrive.get_account_email()
    if not recipient:
        return

    msg = MIMEText(message)
    msg["Subject"] = "Cloud Upload finished"
    msg["From"] = settings.SMTP_USER
    msg["To"] = recipient

    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
            smtp.sendmail(settings.SMTP_USER, [recipient], msg.as_string())
    except Exception as exc:
        print(f"Email notification failed: {exc}")
