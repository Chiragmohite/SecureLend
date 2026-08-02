"""
assistant.py
------------
"Ask the bank" support chatbot. Currently rule-based (keyword matching
against an FAQ), NOT an LLM -- no Grok/OpenAI API key is configured for
this project. Structured deliberately so swapping in a real LLM later is
a single-function change: replace the body of get_bot_reply() with an API
call (see the commented example at the bottom) and nothing else in the
app needs to change, since the function signature (question in, answer +
matched-topic out) stays the same.

This is intentionally similar in spirit to sms.py/email_sender.py's
"real-if-configured, simulated otherwise" pattern -- except here, since
there's no key at all yet, it's rule-based FAQ matching all the way
through. When a key is added, GROK_API_KEY (or OPENAI_API_KEY) being set
is what should gate which path runs, exactly like TWILIO_* / SMTP_* do
elsewhere in this codebase.
"""
import re
from typing import Tuple

# Each entry: (topic name, keyword patterns, answer). Matched in order;
# first match wins. Keep answers short, factual, and about THIS app --
# this is not a general-knowledge chatbot.
FAQ = [
    ("interest_rate", [r"\binterest\b", r"\brate\b", r"\bp\.?a\.?\b"],
     "Interest rates are risk-based, not fixed: they range from 10.5% to 20% p.a. "
     "depending on your profile (bank balance stability, employment type, income "
     "consistency, and KYC completeness). Your exact rate is shown after you apply, "
     "in the eligibility breakdown."),

    ("tenure", [r"\btenure\b", r"\brepay(ment)?\b", r"\bmonths?\b", r"\bemi\b"],
     "You can choose a repayment tenure of 12, 24, 36, 48, or 60 months when applying. "
     "A longer tenure lowers your monthly EMI but your affordability is checked against "
     "whichever tenure you pick."),

    ("eligibility", [r"\beligib", r"\bapprov", r"\breject", r"\bscore\b", r"\bcriteria\b"],
     "Eligibility is scored out of 100 across six factors: loan affordability (35), "
     "bank balance stability (20), employment stability (15), existing EMI headroom (10), "
     "income consistency (15), and KYC completeness (5). Score 70+ is Approved, 50-69 is "
     "Manual Review, below 50 is Rejected. Some conditions (like an unaffordable EMI, or a "
     "big mismatch between your declared and bank-observed income) can override the score "
     "entirely -- you'll always see the exact reason in your results."),

    ("documents", [r"\bsalary slip\b", r"\bdocument", r"\bincome proof\b", r"\bupload\b", r"\bcollateral\b"],
     "Loans of ₹5,00,000 or more require a salary slip / income proof upload before they "
     "can be approved -- this is your uploaded document being used as supporting evidence "
     "for the income you declare. Smaller loans don't require this."),

    ("security", [r"\bsecur", r"\bids\b", r"\bprotect", r"\bhack", r"\bsafe\b", r"\bencrypt"],
     "SecureLend runs a hybrid intrusion detection system: rule-based checks (SQL "
     "injection, XSS, brute-force login detection, malicious file uploads, rate limiting) "
     "plus a trained ML anomaly detector. You can see live (aggregated, non-identifying) "
     "stats on the Security page."),

    ("otp", [r"\botp\b", r"\bsms\b", r"\bphone verif"],
     "We send a one-time password to verify your phone number during registration. "
     "If real SMS delivery isn't configured on this deployment, the OTP is shown directly "
     "in the app instead, purely for demo purposes."),

    ("face_iris", [r"\bface\b", r"\biris\b", r"\bbiometric", r"\bcamera\b"],
     "Face verification uses your camera to confirm a live person is registering the "
     "account. The optional iris step uses real on-device ML (MediaPipe) to detect your "
     "iris -- the detection is real, but the final match decision is simulated, since real "
     "biometric authentication needs an enrolled template and infrared hardware."),

    ("account_lockout", [r"\block", r"\bblock", r"\bwrong password\b", r"\bfailed login\b"],
     "For your protection, an IP is temporarily blocked after 5 failed login attempts "
     "within 5 minutes, and blocked for a full 24 hours after 3 failed attempts on the "
     "same account in a day."),

    ("contact_human", [r"\bhuman\b", r"\bagent\b", r"\bcall\b", r"\bbranch\b", r"\bspeak to\b", r"\btalk to\b"],
     "This is a demo project without a real support line. In a production deployment, "
     "this is where we'd hand off to a human banker or support queue."),
]

FALLBACK = (
    "I don't have a confident answer for that from what's on this platform. "
    "Try asking about interest rates, tenure, eligibility, required documents, "
    "security, OTP, biometric verification, or account lockouts."
)


async def get_bot_reply(question: str) -> Tuple[str, str]:
    """Returns (answer, matched_topic). matched_topic is 'fallback' if neither
    the FAQ nor the LLM fallback below could help, or 'llm_fallback' if the
    LLM answered using grounded FAQ context.

    Order of operations, and why: the keyword FAQ is tried FIRST and always
    wins on a match -- it's instant, has zero hallucination risk, and this
    bot states specific real numbers (rates, scoring weights, tenure options)
    that must stay exactly correct. The LLM is only invoked for genuinely
    unmatched questions, and even then it's given the actual FAQ text as
    grounding context in its prompt (see llm_reviewer.answer_with_faq_grounding)
    rather than being asked to answer freely -- this keeps it from inventing
    numbers that don't match the real scoring engine, and reduces (does not
    eliminate) prompt-injection risk on this public, unauthenticated endpoint,
    since the model is steered toward restating grounded facts rather than
    improvising."""
    q = question.lower()
    for topic, patterns, answer in FAQ:
        if any(re.search(p, q) for p in patterns):
            return answer, topic

    import llm_reviewer
    faq_context = "\n".join(f"- {topic}: {answer}" for topic, _, answer in FAQ)
    llm_answer = await llm_reviewer.answer_with_faq_grounding(question, faq_context)
    if llm_answer:
        return llm_answer, "llm_fallback"
    return FALLBACK, "fallback"


# ---------------------------------------------------------------------------
# To swap in a real LLM later (once you have a Grok/xAI or OpenAI API key),
# replace the body of get_bot_reply with something like:
#
#   import os, requests
#   GROK_API_KEY = os.environ.get("GROK_API_KEY", "")
#
#   def get_bot_reply(question: str) -> Tuple[str, str]:
#       if not GROK_API_KEY:
#           # fall back to the FAQ matching above if no key is configured
#           ...
#       resp = requests.post(
#           "https://api.x.ai/v1/chat/completions",
#           headers={"Authorization": f"Bearer {GROK_API_KEY}"},
#           json={
#               "model": "grok-4",
#               "messages": [
#                   {"role": "system", "content": "You are SecureLend's support assistant..."},
#                   {"role": "user", "content": question},
#               ],
#           },
#           timeout=15,
#       )
#       answer = resp.json()["choices"][0]["message"]["content"]
#       return answer, "llm"
#
# Nothing in server.py or the frontend needs to change for this swap.
# ---------------------------------------------------------------------------