"""Hybrid Intrusion Detection System — rule-based + statistical anomaly.

- Rule Engine: SQLi patterns, brute force, unauthorized admin, malicious uploads,
  aggressive rate limiting.
- Statistical Anomaly: sliding-window request-rate z-score + endpoint diversity
  scored by IsolationForest (fit on synthetic baseline at startup).
"""
import re
import time
import uuid
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest

# ----- OCR configuration -----
# Tesseract's binary isn't on PATH by default on Windows. Set TESSERACT_CMD in
# your .env to the install path, e.g.:
#   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
# If unset, pytesseract falls back to searching PATH (works on Linux/Mac
# where `apt install tesseract-ocr` / `brew install tesseract` puts it there).
TESSERACT_CMD = os.environ.get("TESSERACT_CMD")

# ----- Regex signatures -----
# SQL_WS tolerates inline comments (/* ... */) used as a separator instead of
# whitespace -- e.g. "' OR/**/1=1--" -- a classic evasion technique that a
# plain \s* misses entirely, since /**/ contains no whitespace characters.
SQL_WS = r"(?:\s|/\*.*?\*/)*"

SQLI_PATTERNS = [
    re.compile(r"('|(\%27))" + SQL_WS + r"(or|and)" + SQL_WS + r"('|(\%27))?" + SQL_WS + r"\d+" + SQL_WS + r"=" + SQL_WS + r"\d+", re.I),
    re.compile(r"(\bunion\b\s+\bselect\b)", re.I),
    re.compile(r"(--|#|;)\s*(drop|delete|update|insert)\b", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"\bxp_cmdshell\b", re.I),
    re.compile(r"(\bor\b|\band\b)" + SQL_WS + r"['\"]?1['\"]?" + SQL_WS + r"=" + SQL_WS + r"['\"]?1", re.I),
    re.compile(r"';\s*--", re.I),
    # Comment-truncation auth bypass: a quote immediately (or near-immediately)
    # followed by an inline SQL comment marker -- e.g. "admin'--" -- does not
    # require a semicolon or a drop/delete/update/insert keyword to be a real
    # attack; the quote+comment combination alone is the tell. Legitimate
    # input essentially never contains a literal quote directly followed by
    # -- or #.
    re.compile(r"['\"]\s*(--|#)", re.I),
]

XSS_PATTERNS = [
    re.compile(r"<script[^>]*>", re.I),
    re.compile(r"javascript:", re.I),
    re.compile(r"on\w+\s*=", re.I),
]

BLOCKED_EXTENSIONS = {".exe", ".bat", ".sh", ".php", ".jsp", ".js", ".dll", ".msi", ".cmd", ".vbs"}
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_UPLOAD_MB = 5

# ----- In-memory state -----
_request_log: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))  # ip -> [(ts, endpoint)]
_login_failures: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))  # "ip:email" -> [ts]
_ip_failed_login_ts: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))  # ip -> [ts] for ML feature

# Rate limit thresholds
RATE_WINDOW_SEC = 60
RATE_LIMIT = 60  # >60 req/min → flagged
RATE_HARD_BLOCK = 120  # >120 req/min → blocked
BRUTE_FORCE_LIMIT = 5
BRUTE_FORCE_WINDOW = 300  # 5 min

# Separate, stricter daily rule: independent of the fast 5-in-5-min check
# above, this catches someone spacing out guesses to dodge that window.
DAILY_LOGIN_LIMIT = 3
DAILY_LOGIN_WINDOW = 86400  # 24h
DAILY_LOGIN_BLOCK_MIN = 24 * 60  # block for a full day, not just 15 min
_daily_login_failures: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))  # "ip:email" -> [ts]

# ----- Isolation Forest (trained on synthetic baseline once) -----
_iso_model: Optional[IsolationForest] = None


def train_baseline_model():
    """Train IsolationForest on synthetic normal traffic patterns."""
    global _iso_model
    rng = np.random.default_rng(42)
    # features: [requests_per_min, unique_endpoints, distinct_ids_hit]
    normal = np.column_stack([
        rng.normal(5, 2, 400).clip(0, 30),
        rng.normal(3, 1, 400).clip(1, 8),
        rng.normal(1.5, 0.5, 400).clip(0, 4),
    ])
    _iso_model = IsolationForest(contamination=0.05, random_state=42, n_estimators=80)
    _iso_model.fit(normal)


def _client_ip(request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _record_request(ip: str, endpoint: str):
    _request_log[ip].append((time.time(), endpoint))


def _recent_stats(ip: str) -> tuple[int, int]:
    now = time.time()
    log = _request_log[ip]
    recent = [(t, e) for t, e in log if now - t <= RATE_WINDOW_SEC]
    count = len(recent)
    unique = len({e for _, e in recent})
    return count, unique


def _distinct_id_pattern(ip: str) -> int:
    """Detect sequential ID enumeration."""
    now = time.time()
    ids_seen = set()
    for t, e in _request_log[ip]:
        if now - t > RATE_WINDOW_SEC:
            continue
        m = re.search(r"/(?:users|loans|applications)/([a-zA-Z0-9-]{6,})", e)
        if m:
            ids_seen.add(m.group(1))
    return len(ids_seen)


def scan_payload_for_sqli(text: str) -> Optional[str]:
    if not text:
        return None
    for pat in SQLI_PATTERNS:
        if pat.search(text):
            return pat.pattern
    return None


def scan_payload_for_xss(text: str) -> Optional[str]:
    if not text:
        return None
    for pat in XSS_PATTERNS:
        if pat.search(text):
            return pat.pattern
    return None


def check_upload(filename: str, size_bytes: int) -> Optional[str]:
    if not filename:
        return "empty_filename"
    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if ext in BLOCKED_EXTENSIONS:
        return f"blocked_extension:{ext}"
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return f"disallowed_extension:{ext or 'none'}"
    if size_bytes > MAX_UPLOAD_MB * 1024 * 1024:
        return f"too_large:{size_bytes}"
    return None


# ----- Income-proof content validation -----
# check_upload() above only validates extension + size — a JPG of a cat or a
# blank PDF would pass it. This validates the file actually *looks like* a
# salary slip / income-proof document before we mark KYC as verified.
SALARY_SLIP_KEYWORDS = [
    "salary", "payslip", "pay slip", "net pay", "gross pay", "gross earnings",
    "earnings", "deduction", "basic pay", "basic salary", "hra",
    "house rent allowance", "employee id", "employee name", "ctc",
    "provident fund", "income tax", "tds", "designation", "department",
    "conveyance", "allowance", "professional tax", "uan",
]
MIN_KEYWORD_MATCHES = 3  # distinct keywords required to accept the document


def _extract_pdf_text(contents: bytes) -> str:
    try:
        import pdfplumber
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)
    except Exception:
        return ""


def _extract_image_text(contents: bytes) -> Optional[str]:
    """Returns extracted text, or None if OCR isn't available on this machine
    (Tesseract not installed) — caller should treat None as 'unverifiable',
    not 'invalid'."""
    try:
        import pytesseract
        from PIL import Image
        import io
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        img = Image.open(io.BytesIO(contents))
        return pytesseract.image_to_string(img)
    except Exception:
        return None


def validate_income_proof_content(filename: str, contents: bytes) -> tuple[Optional[str], Optional[str]]:
    """Returns (rejection_reason_or_None, extracted_text_or_None). The
    extracted text is passed along so the caller can also try to pull a
    concrete salary figure out of it (see extract_declared_salary_from_text)
    -- previously this function only checked for salary-slip-*shaped*
    keywords and never looked at the actual number, which meant a declared
    income far above what the uploaded slip actually says would sail
    through unnoticed."""
    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""

    if ext == ".pdf":
        text = _extract_pdf_text(contents)
        if not text.strip():
            # Likely a scanned/image-based PDF with no extractable text layer.
            # Can't verify content without OCR — don't hard-block on this alone.
            return None, None
        text_l = text.lower()
        hits = sum(1 for kw in SALARY_SLIP_KEYWORDS if kw in text_l)
        if hits < MIN_KEYWORD_MATCHES:
            return "content_mismatch: file does not appear to contain salary-slip fields (basic pay, HRA, net pay, deductions, etc.)", None
        return None, text

    if ext in {".jpg", ".jpeg", ".png"}:
        text = _extract_image_text(contents)
        if text is None:
            # OCR unavailable on this machine — can't verify, don't hard-block.
            return None, None
        text_l = text.lower()
        hits = sum(1 for kw in SALARY_SLIP_KEYWORDS if kw in text_l)
        if hits < MIN_KEYWORD_MATCHES:
            return "content_mismatch: image does not appear to contain salary-slip fields (basic pay, HRA, net pay, deductions, etc.)", None
        return None, text

    return None, None


# Field labels checked in priority order -- "net pay"/"take-home" is the
# most trustworthy figure (what the person actually receives), falling back
# to gross/basic if net isn't found on the slip.
_SALARY_FIELD_PATTERNS = [
    r"net\s*pay",
    r"net\s*salary",
    r"take[- ]?home(?:\s*pay)?",
    r"gross\s*earnings",
    r"total\s*earnings",
    r"gross\s*salary",
    r"basic\s*(?:pay|salary)",
]
# Matches amounts like "56,200", "₹56,200", "Rs. 56200.00", "INR 56,200"
_AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr)?\s*([\d]{1,3}(?:,\d{2,3})*|\d{4,})(?:\.\d+)?", re.IGNORECASE)


def extract_declared_salary_from_text(text: Optional[str]) -> Optional[float]:
    """Best-effort extraction of a monthly salary figure from OCR'd/parsed
    payslip text. Looks for common payslip field labels in priority order
    and grabs the first currency-formatted number appearing on that line,
    or on one of the next couple of lines -- OCR on table-based payslips
    frequently splits a label and its value across separate lines (wide
    column spacing gets read as a line break), so restricting the search
    to only the exact same line as the label misses real matches. This is
    a regex heuristic, not a general-purpose document parser -- unusual
    slip layouts may still not extract cleanly, in which case this returns
    None and the caller should treat the mismatch check as unavailable for
    that upload (fail open, not closed) rather than blocking someone over
    a parsing miss."""
    if not text:
        return None
    lines = text.splitlines()
    # How many lines after a label match to look for its value -- covers
    # "label on its own line, value on the next" table-OCR splits without
    # wandering so far it picks up an unrelated number.
    LOOKAHEAD = 2
    for pattern in _SALARY_FIELD_PATTERNS:
        for i, line in enumerate(lines):
            if not re.search(pattern, line, re.IGNORECASE):
                continue
            for candidate_line in lines[i:i + 1 + LOOKAHEAD]:
                amounts = _AMOUNT_RE.findall(candidate_line)
                for raw in amounts:
                    try:
                        val = float(raw.replace(",", ""))
                    except ValueError:
                        continue
                    # Sanity bounds: ignore stray small numbers (e.g. "12%"
                    # deduction rates, employee IDs) and implausible values.
                    if 1000 <= val <= 10_000_000:
                        return val
    return None


def register_login_failure(ip: str, email: str) -> bool:
    """Return True if brute-force threshold exceeded."""
    key = f"{ip}:{email.lower()}"
    now = time.time()
    q = _login_failures[key]
    q.append(now)
    _ip_failed_login_ts[ip].append(now)
    recent = [t for t in q if now - t <= BRUTE_FORCE_WINDOW]
    return len(recent) >= BRUTE_FORCE_LIMIT


def register_daily_login_failure(ip: str, email: str) -> bool:
    """Separate 24h counter: True if 3+ failed attempts for this ip+email
    today, independent of the fast 5-in-5-min brute-force check above.
    This catches slow/spaced-out guessing that dodges the fast window."""
    key = f"{ip}:{email.lower()}"
    now = time.time()
    q = _daily_login_failures[key]
    q.append(now)
    recent = [t for t in q if now - t <= DAILY_LOGIN_WINDOW]
    return len(recent) >= DAILY_LOGIN_LIMIT


def clear_daily_login_failures(ip: str, email: str):
    key = f"{ip}:{email.lower()}"
    if key in _daily_login_failures:
        _daily_login_failures[key].clear()


def failed_logins_5min(ip: str) -> int:
    now = time.time()
    return sum(1 for t in _ip_failed_login_ts[ip] if now - t <= 300)


def clear_login_failures(ip: str, email: str):
    key = f"{ip}:{email.lower()}"
    if key in _login_failures:
        _login_failures[key].clear()


async def log_attack(db, *, ip: str, attack_type: str, endpoint: str,
                     status: str, details: str = "", user_id: Optional[str] = None,
                     severity: str = "medium", source: str = "rule"):
    doc = {
        "id": str(uuid.uuid4()),
        "ip_address": ip,
        "attack_type": attack_type,
        "endpoint": endpoint,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,  # blocked | flagged
        "severity": severity,  # low | medium | high | critical
        "source": source,  # rule | ml
        "details": details,
    }
    await db.attack_logs.insert_one(doc)
    return doc


async def log_ml_inference(db, *, ip: str, endpoint: str, features: dict, verdict: dict):
    """Persists the raw feature vector AND the model's verdict for every
    ML-scored request -- not just the ones that got blocked/flagged, but
    genuinely normal-looking traffic too. This is what makes real
    validation possible later: attack_logs only ever stored the final
    label, never the actual numbers fed into the model, so past traffic
    can never be replayed or checked against a retrained model. This
    collection is the fix -- going forward, this *is* real captured
    traffic (distinct from the synthetic training set in
    ml/train_ids_model.py), and can be pulled into a genuine held-out
    validation set once enough accumulates.
    """
    doc = {
        "id": str(uuid.uuid4()),
        "ip_address": ip,
        "endpoint": endpoint,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": features,
        "predicted_type": verdict.get("predicted_type"),
        "confidence": verdict.get("confidence"),
        "anomaly_score": verdict.get("anomaly_score"),
        "action": verdict.get("action"),
        # Filled in later by a human reviewing real traffic (or by a
        # deliberate test script that knows what it sent) -- None until
        # then. This is what turns "captured traffic" into a genuine
        # labeled validation set rather than just a request log.
        "true_label": None,
    }
    await db.ml_inference_log.insert_one(doc)
    return doc


async def block_ip(db, ip: str, reason: str, duration_min: int = 15):
    now = datetime.now(timezone.utc)
    await db.blocked_ips.update_one(
        {"ip_address": ip, "unblocked_at": None},
        {"$setOnInsert": {
            "id": str(uuid.uuid4()),
            "ip_address": ip,
            "reason": reason,
            "blocked_at": now.isoformat(),
            "expires_at": (now.timestamp() + duration_min * 60),
            "unblocked_at": None,
        }},
        upsert=True,
    )


async def is_ip_blocked(db, ip: str) -> bool:
    doc = await db.blocked_ips.find_one({"ip_address": ip, "unblocked_at": None})
    if not doc:
        return False
    # auto-expire
    if doc.get("expires_at") and time.time() > doc["expires_at"]:
        await db.blocked_ips.update_one(
            {"id": doc["id"]},
            {"$set": {"unblocked_at": datetime.now(timezone.utc).isoformat()}},
        )
        return False
    return True


def anomaly_score(ip: str) -> tuple[float, dict]:
    """Return (anomaly_score, feature_dict). Higher = more anomalous."""
    count, unique = _recent_stats(ip)
    id_diversity = _distinct_id_pattern(ip)
    features = {"rpm": count, "unique_endpoints": unique, "id_diversity": id_diversity}
    # need enough traffic to score meaningfully
    if _iso_model is None or count < 15:
        return 0.0, features
    X = np.array([[count, unique, id_diversity]])
    raw = _iso_model.score_samples(X)[0]
    anomaly = float(max(0.0, -raw))
    return anomaly, features


# ============ Custom-trained ML model (Random Forest + IsolationForest) ============
_ml_scorer = None  # lazy — score_request callable

SQL_KEYWORDS = re.compile(
    r"\b(select|union|insert|update|delete|drop|alter|exec|xp_cmdshell)\b"
    r"|--"          # SQL line comment -- deliberately NOT \b-wrapped, since -- is
                     # punctuation on both sides and \b never matches there (this
                     # was silently broken before: `' OR 1=1 --` matched nothing)
    r"|/\*"         # SQL block comment start
    r"|\bor\b\s*['\"]?\s*\d+\s*=\s*\d+"    # classic tautology: OR 1=1
    r"|\band\b\s*['\"]?\s*\d+\s*=\s*\d+"   # classic tautology: AND 1=1
    r"|\bor\b\s*['\"]\s*\w*\s*['\"]\s*=\s*['\"]?\s*\w*",  # OR '1'='1' (string form)
    re.I,
)
SCRIPT_TAG_RE = re.compile(r"<\s*script\b|javascript:|on\w+\s*=", re.I)


def load_ml_scorer():
    """Lazy-load the trained model bundle (attack_classifier + anomaly_detector)."""
    global _ml_scorer
    if _ml_scorer is not None:
        return _ml_scorer
    try:
        from ml.ids_inference import score_request  # noqa: WPS433
        _ml_scorer = score_request
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger(__name__).exception("ML scorer failed to load: %s", e)
        _ml_scorer = None
    return _ml_scorer


def endpoint_sensitivity(path: str) -> int:
    """0=public, 1=authenticated, 2=admin-only."""
    if path.startswith("/api/admin/"):
        return 2
    public = {"/api/", "/api/health", "/api/auth/login", "/api/auth/register",
              "/api/otp/send", "/api/otp/verify", "/api/kyc/pan-check",
              "/api/bank/list"}
    if path in public:
        return 0
    return 1


def file_ext_risk_from_payload(payload_text: str) -> int:
    lower = payload_text.lower()
    for ext in BLOCKED_EXTENSIONS:
        if ext in lower:
            return 1
    return 0


def build_features(*, ip: str, path: str, role: Optional[str],
                   payload_text: str, payload_bytes: int) -> dict:
    """Compute the 10 features the trained model expects."""
    count, unique = _recent_stats(ip)
    sens = endpoint_sensitivity(path)
    role_mismatch = 1 if (sens == 2 and role != "admin") else 0
    return {
        "requests_per_minute": int(count),
        "failed_logins_5min": int(failed_logins_5min(ip)),
        "contains_sql_keywords": 1 if SQL_KEYWORDS.search(payload_text or "") else 0,
        "contains_script_tag": 1 if SCRIPT_TAG_RE.search(payload_text or "") else 0,
        "endpoint_sensitivity": sens,
        "role_mismatch": role_mismatch,
        "file_ext_risk": file_ext_risk_from_payload(payload_text or ""),
        "payload_size_kb": round(payload_bytes / 1024.0, 3),
        "unique_endpoints_1min": int(unique),
        "hour_of_day": datetime.now(timezone.utc).hour,
    }


# Human-friendly names for the classifier's label output
ML_LABEL_TO_ATTACK = {
    "sql_injection": "SQL Injection",
    "brute_force_login": "Brute Force Login",
    "bot_flood": "Bot Flood",
    "unauthorized_admin": "Unauthorized Admin Access",
    "malicious_upload": "Malicious File Upload",
    "xss_attempt": "XSS Attempt",
    "anomalous_traffic": "Anomalous Traffic",
    "normal": "Normal",
}