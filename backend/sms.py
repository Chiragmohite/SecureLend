"""
sms.py
------
Real SMS delivery via Twilio, with automatic fallback to demo mode when
Twilio credentials aren't configured. This means the app behaves exactly
as before (OTP shown in the API response, no real SMS) until you add
Twilio credentials to .env — at which point it silently switches to
sending real text messages instead.

Setup (free, no payment required for testing):
1. Sign up at https://www.twilio.com/try-twilio (free trial account).
2. From the Twilio Console dashboard, copy your Account SID and Auth Token.
3. Get a free Twilio trial phone number (Console > Phone Numbers > Buy a number
   -> trial accounts get one free number).
4. IMPORTANT: Twilio trial accounts can only send SMS to phone numbers you've
   manually "verified" in the Twilio Console (Console > Phone Numbers >
   Verified Caller IDs). Add your own number there for real-SMS testing/demo.
5. Add to backend/.env:
     TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     TWILIO_AUTH_TOKEN=your_auth_token_here
     TWILIO_FROM_NUMBER=+1xxxxxxxxxx   (the Twilio number from step 3)

If any of these three env vars are missing, send_real_sms() returns False
and the caller falls back to demo mode automatically -- nothing breaks.
"""

import os
import logging

logger = logging.getLogger("securelend")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

_twilio_client = None
_TWILIO_CONFIGURED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)

if _TWILIO_CONFIGURED:
    try:
        from twilio.rest import Client
        _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("[SMS] Twilio configured — real SMS delivery enabled")
    except Exception as e:
        logger.warning(f"[SMS] Twilio configured but failed to initialize ({e}) — falling back to demo mode")
        _TWILIO_CONFIGURED = False
else:
    logger.info("[SMS] Twilio not configured — running in demo mode (OTP shown in API response)")


def sms_is_configured() -> bool:
    return _TWILIO_CONFIGURED


def send_real_sms(phone_10digit: str, message: str) -> bool:
    """
    Attempts to send a real SMS via Twilio to an Indian 10-digit number.
    Returns True if the send succeeded, False otherwise (caller should
    fall back to demo behavior on False).
    """
    if not _TWILIO_CONFIGURED or _twilio_client is None:
        return False
    try:
        to_number = f"+91{phone_10digit}"
        _twilio_client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=to_number,
        )
        logger.info(f"[SMS] Real SMS sent to {to_number}")
        return True
    except Exception as e:
        logger.warning(f"[SMS] Failed to send real SMS to +91{phone_10digit}: {e}")
        return False