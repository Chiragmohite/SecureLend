"""
email_sender.py
----------------
Real email delivery via SMTP, with automatic fallback to demo mode (logs
the email instead of sending it) when SMTP credentials aren't configured.
Mirrors sms.py's pattern exactly.

Setup with a Gmail account (free):
1. Turn on 2-Step Verification on the Gmail account you want to send from:
   https://myaccount.google.com/security
2. Create an "App Password": https://myaccount.google.com/apppasswords
   (choose app "Mail", device "Other" -> name it "SecureLend") -> copy the
   16-character password it gives you (spaces don't matter).
3. Add to backend/.env:
     SMTP_HOST=smtp.gmail.com
     SMTP_PORT=587
     SMTP_USER=youraddress@gmail.com
     SMTP_PASSWORD=your16charapppassword
     SMTP_FROM_NAME=SecureLend

Any other SMTP provider (Outlook, a college email, SendGrid's SMTP relay,
etc.) works the same way -- just change SMTP_HOST/PORT to match.

If any of SMTP_HOST/SMTP_USER/SMTP_PASSWORD is missing, send_real_email()
returns False and the caller falls back to demo mode (logs it) automatically.
"""

import os
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("securelend")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "SecureLend")

_SMTP_CONFIGURED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)

if _SMTP_CONFIGURED:
    logger.info("[Email] SMTP configured — real email delivery enabled")
else:
    logger.info("[Email] SMTP not configured — running in demo mode (emails logged, not sent)")


def email_is_configured() -> bool:
    return _SMTP_CONFIGURED


def send_real_email(to_email: str, subject: str, body_text: str, attachment_bytes: bytes = None,
                     attachment_filename: str = "attachment.pdf") -> bool:
    """
    Attempts to send a real email via SMTP (STARTTLS), optionally with a
    PDF attachment. Returns True if the send succeeded, False otherwise
    (caller should fall back to demo behavior -- e.g. just logging -- on False).
    """
    if not _SMTP_CONFIGURED:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        msg["To"] = to_email
        msg.set_content(body_text)

        if attachment_bytes:
            msg.add_attachment(attachment_bytes, maintype="application", subtype="pdf",
                                filename=attachment_filename)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"[Email] Real email sent to {to_email}")
        return True
    except Exception as e:
        logger.warning(f"[Email] Failed to send real email to {to_email}: {e}")
        return False