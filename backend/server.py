"""SecureLend backend — NBFC loan platform with Hybrid IDS."""
from dotenv import load_dotenv
from pathlib import Path
import os
load_dotenv(Path(__file__).parent / ".env")

import re
import json
import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

import auth as auth_mod
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
from scoring import score_loan
import ids
import llm_reviewer
import face_match
from seed import seed_admin, seed_demo_data
from sms import send_real_sms, sms_is_configured
from email_sender import send_real_email, email_is_configured
from pdf_gen import generate_sanction_letter
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("securelend")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="SecureLend API")

# ---------- Public paths that skip IDS admin gate ----------
PUBLIC_PATHS = {"/", "/api/", "/api/health"}

# ---------- File-upload endpoints ----------
# These send raw binary (PDF/JPG/PNG) inside a multipart body. Decoding binary
# bytes as UTF-8 and scanning them for SQL/XSS keyword text is unreliable —
# stripped/garbled binary noise can coincidentally contain substrings like
# "or", "and", "--", ";", or "select", producing false-positive SQLi/XSS hits
# purely by chance. These endpoints already get dedicated validation via
# ids.check_upload() (extension allow-list + size limit), so we skip the
# text-based content scan and the two text-derived ML features for them.
UPLOAD_ENDPOINTS = {"/api/kyc/income-proof", "/api/upload/kyc"}


# ============ Hybrid IDS Middleware (pure ASGI) ============
class HybridIDSMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not path.startswith("/api"):
            return await self.app(scope, receive, send)

        # Build lightweight Request for helpers
        request = Request(scope, receive=receive)
        ip = ids._client_ip(request)
        ids._record_request(ip, path)

        # Resolve caller role (used both for feature extraction and admin gate)
        tok = auth_mod.extract_token(request)
        role = None
        if tok:
            try:
                role = auth_mod.decode_token(tok).get("role")
            except Exception:
                role = None

        # 1) blocked ip
        # Exception: an authenticated admin hitting the blocked-IPs
        # management routes specifically (view / unblock) is let through
        # even if their own IP is on the block list. Without this, an
        # admin whose IP gets blocked (e.g. from their own security
        # testing) can't use the dashboard's own "Unblock" button to fix
        # it -- that request is itself under /api/* and would get
        # rejected by this same check before ever reaching the route
        # handler. Everything else stays blocked as normal; this doesn't
        # touch the block for any other endpoint.
        is_self_service_unblock_route = (
            role == "admin"
            and (path == "/api/admin/blocked-ips" or re.match(r"^/api/admin/blocked-ips/[^/]+/unblock$", path))
        )
        if not is_self_service_unblock_route and await ids.is_ip_blocked(db, ip):
            await ids.log_attack(db, ip=ip, attack_type="Blocked IP Attempt",
                                 endpoint=path, status="blocked",
                                 details="IP is on active block list", severity="high",
                                 source="rule")
            return await self._reject(send, 403, "Your IP is temporarily blocked due to suspicious activity.")

        # 2) Buffer body so downstream can still read it
        body_chunks = []
        method = scope.get("method", "GET")
        if method in ("POST", "PUT", "PATCH"):
            more = True
            while more:
                msg = await receive()
                if msg["type"] == "http.request":
                    body_chunks.append(msg.get("body", b""))
                    more = msg.get("more_body", False)
                else:
                    more = False
        body = b"".join(body_chunks)
        content_type = (scope.get("headers") or [])
        content_type = next((v.decode("latin-1") for k, v in content_type if k == b"content-type"), "")
        is_file_upload = path in UPLOAD_ENDPOINTS or content_type.startswith("multipart/form-data")

        # For file-upload endpoints, don't decode raw binary (PDF/JPG/PNG) bytes
        # as text for keyword scanning — binary noise can coincidentally match
        # SQLi/XSS patterns. Only scan the query string there; ids.check_upload()
        # (extension + size validation) is the real guard for these routes.
        if is_file_upload:
            payload_text = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        else:
            payload_text = body.decode("utf-8", errors="ignore") + " " + (scope.get("query_string", b"").decode("utf-8", errors="ignore"))

        # Compute the feature vector once, here, before any rule check --
        # not just before the ML step. Previously this only happened at
        # step 5, so anything the RULE engine blocked (SQLi, XSS, rate
        # limit, unauthorized admin) never got its features captured at
        # all, since the request returned early before reaching step 5.
        # That made log_ml_inference's "real captured traffic" dataset
        # blind to everything the rules already catch -- only normal
        # traffic and ML-only catches ever showed up. Computing it here
        # means every processed request gets logged, regardless of which
        # layer (rule or ML) ultimately handles it.
        features = ids.build_features(
            ip=ip, path=path, role=role,
            payload_text=payload_text, payload_bytes=len(body),
        )

        sqli_hit = ids.scan_payload_for_sqli(payload_text)
        if sqli_hit:
            await ids.log_attack(db, ip=ip, attack_type="SQL Injection",
                                 endpoint=path, status="blocked",
                                 details=f"Pattern matched: {sqli_hit[:80]}", severity="critical",
                                 source="rule")
            await ids.log_ml_inference(db, ip=ip, endpoint=path, features=features, verdict={
                "predicted_type": "sql_injection", "confidence": None,
                "anomaly_score": None, "action": "block",
            })
            return await self._reject(send, 400, "Malicious input detected. Request blocked.")

        xss_hit = ids.scan_payload_for_xss(payload_text)
        if xss_hit:
            await ids.log_attack(db, ip=ip, attack_type="XSS Attempt",
                                 endpoint=path, status="blocked",
                                 details=f"Pattern matched: {xss_hit[:80]}", severity="high",
                                 source="rule")
            await ids.log_ml_inference(db, ip=ip, endpoint=path, features=features, verdict={
                "predicted_type": "xss_attempt", "confidence": None,
                "anomaly_score": None, "action": "block",
            })
            return await self._reject(send, 400, "Malicious input detected.")

        # 3) Rate limiting (rule engine)
        # Same exemption as (1) applies here -- without it, an admin's
        # accumulated request count (from their own testing + the
        # dashboard's own polling, which all counts against the same IP
        # across every endpoint) can immediately re-trigger a *fresh*
        # block via this check the instant the earlier block is bypassed,
        # trapping the admin in a loop between the two checks.
        count, unique = ids._recent_stats(ip)
        if count > ids.RATE_HARD_BLOCK and not is_self_service_unblock_route:
            await ids.block_ip(db, ip, "Bot Flood / DoS")
            await ids.log_attack(db, ip=ip, attack_type="Bot Flood",
                                 endpoint=path, status="blocked",
                                 details=f"{count} requests/min", severity="high",
                                 source="rule")
            await ids.log_ml_inference(db, ip=ip, endpoint=path, features=features, verdict={
                "predicted_type": "bot_flood", "confidence": None,
                "anomaly_score": None, "action": "block",
            })
            return await self._reject(send, 429, "Rate limit exceeded. IP blocked.")
        if count > ids.RATE_LIMIT:
            await ids.log_attack(db, ip=ip, attack_type="Rate Limit Exceeded",
                                 endpoint=path, status="flagged",
                                 details=f"{count} requests/min", severity="medium",
                                 source="rule")

        # 4) Unauthorized admin route (rule engine)
        if path.startswith("/api/admin/") and role != "admin":
            await ids.log_attack(db, ip=ip, attack_type="Unauthorized Admin Access",
                                 endpoint=path, status="blocked",
                                 details=f"Role={role or 'anonymous'}", severity="high",
                                 source="rule")
            await ids.log_ml_inference(db, ip=ip, endpoint=path, features=features, verdict={
                "predicted_type": "unauthorized_admin", "confidence": None,
                "anomaly_score": None, "action": "block",
            })
            return await self._reject(send, 403, "Admin privileges required.")

        # 5) ============ Custom ML model (Random Forest + IsolationForest) ============
        # Runs alongside the rule engine; can independently block/flag.
        # Skip only for authenticated admins on /api/admin/* to avoid noise from
        # dashboard polling — admins are already role-authenticated by (4).
        skip_ml = path.startswith("/api/admin/") and role == "admin"
        if not skip_ml:
            scorer = ids.load_ml_scorer()
            if scorer is not None:
                try:
                    verdict = scorer(features)
                    await ids.log_ml_inference(db, ip=ip, endpoint=path, features=features, verdict=verdict)
                    if verdict["action"] in ("block", "flag"):
                        pretty = ids.ML_LABEL_TO_ATTACK.get(
                            verdict["predicted_type"], verdict["predicted_type"]
                        )
                        details = (
                            f"predicted={verdict['predicted_type']} "
                            f"conf={verdict['confidence']:.3f} "
                            f"anomaly={verdict['anomaly_score']:.3f} "
                            f"(thr={verdict['anomaly_threshold']:.3f})"
                        )
                        effective_action = verdict["action"]
                        if effective_action == "block" and path in UPLOAD_ENDPOINTS:
                            # These endpoints already have dedicated rule-based
                            # guards: ids.check_upload() (extension + size) and
                            # ids.validate_income_proof_content() (keyword match
                            # against extracted text). The ML model's features
                            # can't reliably tell a large *legitimate* PDF/JPG
                            # apart from a malicious one here -- payload_size_kb
                            # alone correlates with its synthetic malicious_upload
                            # class, so a real salary slip gets blocked purely for
                            # being a normal-sized file. Downgrade to a flag
                            # (still visible in the Attack Feed / ML Health tab)
                            # instead of hard-rejecting a legitimate upload.
                            effective_action = "flag"
                            details += " [downgraded: block->flag, upload endpoint has dedicated content validation]"
                        await ids.log_attack(
                            db, ip=ip, attack_type=pretty, endpoint=path,
                            status="blocked" if effective_action == "block" else "flagged",
                            severity=verdict["severity"], details=details, source="ml",
                        )
                        if effective_action == "block":
                            return await self._reject(send, 403, f"Blocked by IDS ML model ({pretty}).")
                except Exception as e:
                    import logging
                    logging.getLogger("securelend").warning("ML scorer error: %s", e)

        # Replay body to downstream
        sent = {"done": False}
        async def new_receive():
            if not sent["done"]:
                sent["done"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, new_receive, send)

    async def _reject(self, send, status: int, detail: str):
        import json as _json
        body = _json.dumps({"detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})


app.add_middleware(HybridIDSMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Models ============
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=6)
    dob: str
    phone: str
    pan: str
    # Required 16-float geometric face descriptor computed client-side
    # (see frontend/src/lib/faceEmbedding.js). Previously optional, which
    # meant registration's duplicate-face check (see face_match.py) only
    # ran if the client happened to send one -- skipping face capture
    # entirely skipped real fraud-prevention, not just a decorative step.
    # Required now, matching phone/pan below, so every registration goes
    # through duplicate-face detection.
    face_embedding: list[float]

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if not re.fullmatch(r"[6-9]\d{9}", v):
            raise ValueError("Invalid Indian mobile number")
        return v

    @field_validator("pan")
    @classmethod
    def _pan(cls, v):
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", v.upper()):
            raise ValueError("Invalid PAN format")
        return v.upper()

    @field_validator("face_embedding")
    @classmethod
    def _face_embedding(cls, v):
        # Now that face_embedding is required, a malformed/wrong-length
        # vector must reject the registration outright -- silently
        # dropping it (the old behaviour) would recreate the same bypass
        # this field being required is meant to close.
        if len(v) != face_match.EMBEDDING_LENGTH:
            raise ValueError("Face capture failed -- please redo the face scan step.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OTPSendRequest(BaseModel):
    phone: str


class OTPVerifyRequest(BaseModel):
    phone: str
    otp: str


class PANVerifyRequest(BaseModel):
    pan: str


class BankConnectRequest(BaseModel):
    bank_name: str
    consent: bool


class LoanApplyRequest(BaseModel):
    loan_amount: float = Field(gt=0)
    employment_type: str
    monthly_salary: float = Field(ge=0)
    existing_emi: float = Field(default=0, ge=0)
    purpose: str
    # Default of 36 keeps this backward-compatible with any client that
    # hasn't been updated to send a tenure yet.
    tenure_months: int = Field(default=36, ge=6, le=84)

    # Plausibility floor: a declared income like Rs.10/month isn't a real
    # answer -- without this, such a value sails straight into scoring.py
    # and produces a technically-consistent-looking score breakdown (other,
    # genuinely-verified factors like bank stability and employment type
    # score normally, since they don't depend on this field) even though
    # the input itself is obvious nonsense. Reject it as invalid input
    # up front instead, the same way phone/PAN format is rejected above,
    # rather than letting the scorer produce a misleadingly "explainable"
    # result from a joke value. Rs.1,000/month is a deliberately low floor
    # (well under any real minimum wage figure) so this only catches
    # genuinely implausible values, not just low-but-real income.
    @field_validator("monthly_salary")
    @classmethod
    def _monthly_salary_plausible(cls, v):
        if 0 < v < 1000:
            raise ValueError(
                "That doesn't look like a realistic monthly income. "
                "Please enter your actual monthly income in rupees."
            )
        return v

    # Cross-field check: existing_emi is only implausible RELATIVE to
    # declared income -- there's no sensible absolute cap on its own (a high
    # earner can genuinely have a high EMI). Catches likely data-entry
    # errors (an extra zero or two typed in) rather than penalizing a
    # genuinely high-but-real debt burden -- the scorer already handles
    # that correctly on its own by flooring obligation_headroom at 0
    # (see scoring.py), it just shouldn't be fed an obvious typo. 10x
    # monthly income as a single EMI is far beyond anything a real lender
    # would have already approved, so this is a generous, not strict, cap.
    @model_validator(mode="after")
    def _existing_emi_plausible(self):
        if self.monthly_salary > 0 and self.existing_emi > self.monthly_salary * 10:
            raise ValueError(
                "Your existing EMI looks implausibly high compared to your declared "
                "income -- please double-check the amount you entered."
            )
        return self


api = APIRouter(prefix="/api")


# ============ Health ============
@api.get("/")
async def root():
    return {"message": "SecureLend API online", "version": "1.0"}


@api.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ============ Auth ============
def _set_cookies(response: Response, token: str):
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=8 * 3600, path="/",
    )


def _clear_cookies(response: Response):
    response.delete_cookie("access_token", path="/")


@api.post("/auth/register")
async def register(req: RegisterRequest, response: Response):
    email = req.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await db.users.find_one({"pan": req.pan}):
        raise HTTPException(status_code=400, detail="PAN already registered")
    if await db.users.find_one({"phone": req.phone}):
        raise HTTPException(status_code=400, detail="Phone already registered")

    if req.face_embedding:
        existing_faces = [
            (u["id"], u["face_embedding"])
            async for u in db.users.find(
                {"face_embedding": {"$exists": True, "$ne": None}}, {"id": 1, "face_embedding": 1}
            )
        ]
        closest = face_match.closest_face_distance(req.face_embedding, existing_faces)
        if closest:
            logger.info(
                f"[Face] Closest existing match distance: {closest[1]:.4f} "
                f"(threshold: {face_match.DUPLICATE_FACE_THRESHOLD}) against user {closest[0]}"
            )
        dup_user_id = face_match.find_duplicate_face(req.face_embedding, existing_faces)
        if dup_user_id:
            logger.warning(f"[Face] Duplicate-face registration attempt blocked (matches existing user {dup_user_id})")
            raise HTTPException(
                status_code=409,
                detail=(
                    "This face appears to already be linked to another registered account. "
                    "If this is you, please sign in to your existing account instead."
                ),
            )

    uid = str(uuid.uuid4())
    doc = {
        "id": uid,
        "email": email,
        "password_hash": hash_password(req.password),
        "full_name": req.full_name,
        "phone": req.phone,
        "phone_verified": True,  # verified via OTP step already
        "pan": req.pan,
        "pan_verified": True,
        "dob": req.dob,
        "role": "user",
        "face_embedding": req.face_embedding,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    tok = create_access_token(uid, email, "user")
    _set_cookies(response, tok)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    doc.pop("face_embedding", None)
    return {"user": doc, "token": tok}


@api.post("/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    ip = ids._client_ip(request)
    email = req.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user["password_hash"]):
        exceeded = await ids.register_login_failure(db, ip, email)
        daily_exceeded = await ids.register_daily_login_failure(db, ip, email)
        if daily_exceeded:
            await ids.block_ip(db, ip, "Daily Failed-Login Limit (3/day)", duration_min=ids.DAILY_LOGIN_BLOCK_MIN)
            await ids.log_attack(db, ip=ip, attack_type="Daily Login Lockout",
                                 endpoint="/api/auth/login", status="blocked",
                                 details=f"3+ failures today for {email}", severity="high",
                                 source="rule")
            raise HTTPException(status_code=429, detail="Too many failed attempts today. This IP is blocked for 24 hours.")
        if exceeded:
            await ids.block_ip(db, ip, "Brute Force Login")
            await ids.log_attack(db, ip=ip, attack_type="Brute Force Login",
                                 endpoint="/api/auth/login", status="blocked",
                                 details=f"5+ failures for {email}", severity="high",
                                 source="rule")
            raise HTTPException(status_code=429, detail="Too many failed attempts. IP temporarily blocked.")
        await ids.log_attack(db, ip=ip, attack_type="Failed Login",
                             endpoint="/api/auth/login", status="flagged",
                             details=f"email={email}", severity="low",
                             source="rule")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    await ids.clear_login_failures(db, ip, email)
    await ids.clear_daily_login_failures(db, ip, email)
    tok = create_access_token(user["id"], user["email"], user["role"])
    _set_cookies(response, tok)
    user.pop("password_hash", None)
    user.pop("_id", None)
    user.pop("face_embedding", None)
    return {"user": user, "token": tok}


@api.post("/auth/logout")
async def logout(response: Response):
    _clear_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(request: Request):
    user = await get_current_user(request, db)
    return user


# ============ OTP (simulated) ============
_otp_store: dict[str, tuple[str, float]] = {}  # phone -> (otp, expires_at_ts)


@api.post("/otp/send")
async def send_otp(req: OTPSendRequest):
    if not re.fullmatch(r"[6-9]\d{9}", req.phone):
        raise HTTPException(status_code=400, detail="Invalid phone")
    otp = f"{uuid.uuid4().int % 1000000:06d}"
    _otp_store[req.phone] = (otp, time.time() + 300)
    logger.info(f"[OTP] {req.phone} -> {otp}")

    message = f"Your SecureLend verification code is {otp}. Valid for 5 minutes."
    sent_real = send_real_sms(req.phone, message)

    if sent_real:
        return {"sent": True, "demo_otp": None, "real_sms": True,
                "message": f"OTP sent via SMS to +91-{req.phone}"}
    else:
        return {"sent": True, "demo_otp": otp, "real_sms": False,
                "message": f"OTP sent to +91-{req.phone} (demo mode)"}

@api.post("/otp/verify")
async def verify_otp(req: OTPVerifyRequest):
    entry = _otp_store.get(req.phone)
    if not entry:
        raise HTTPException(status_code=400, detail="No OTP requested for this phone")
    otp, exp = entry
    if time.time() > exp:
        raise HTTPException(status_code=400, detail="OTP expired")
    if req.otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    _otp_store.pop(req.phone, None)
    return {"verified": True}


# ============ PAN Verification (mocked) ============
@api.post("/kyc/pan-check")
async def pan_check(req: PANVerifyRequest):
    pan = req.pan.upper()
    if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        raise HTTPException(status_code=400, detail="Invalid PAN format")
    exists = await db.users.find_one({"pan": pan})
    if exists:
        raise HTTPException(status_code=400, detail="PAN already registered")
    return {"valid": True, "pan": pan, "message": "PAN format valid & available"}


# ============ Bank Connection ============
BANKS_DIR = {
    "SBI": "State Bank of India",
    "HDFC": "HDFC Bank",
    "ICICI": "ICICI Bank",
    "Axis": "Axis Bank",
}


@api.get("/bank/list")
async def bank_list():
    return [{"code": k, "name": v} for k, v in BANKS_DIR.items()]


@api.post("/bank/connect")
async def bank_connect(req: BankConnectRequest, request: Request):
    if not req.consent:
        raise HTTPException(status_code=400, detail="Explicit consent required to link bank account")
    if req.bank_name not in BANKS_DIR:
        raise HTTPException(status_code=400, detail="Unsupported bank")
    user = await get_current_user(request, db)
    import random
    monthly_income = random.choice([48000, 65000, 82000, 105000, 135000])
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "bank_name": req.bank_name,
        "account_masked": f"XXXX-XXXX-{random.randint(1000, 9999)}",
        "monthly_income": monthly_income,
        "avg_balance": monthly_income * random.uniform(0.5, 2.4),
        "bank_verified": True,
        "consent_given_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bank_verifications.delete_many({"user_id": user["id"]})
    await db.bank_verifications.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/bank/status")
async def bank_status(request: Request):
    user = await get_current_user(request, db)
    doc = await db.bank_verifications.find_one({"user_id": user["id"]}, {"_id": 0})
    return doc or {}


# ============ Income proof (salary slip) -- required "stake" for large loans ============
# Real lenders require documentary proof of income for larger loans instead of
# taking the applicant's word for it. We require this above a threshold amount.
INCOME_PROOF_REQUIRED_ABOVE = 500000
UPLOADS_DIR = Path(__file__).parent / "uploads"


@api.post("/kyc/income-proof")
async def upload_income_proof(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request, db)
    contents = await file.read()
    size = len(contents)
    violation = ids.check_upload(file.filename, size)
    if violation:
        ip = ids._client_ip(request)
        await ids.log_attack(db, ip=ip, attack_type="Malicious File Upload",
                             endpoint="/api/kyc/income-proof", status="blocked",
                             user_id=user["id"], details=violation, severity="high",
                             source="rule")
        raise HTTPException(status_code=400, detail=f"Upload rejected: {violation}")

    content_violation, extracted_text = ids.validate_income_proof_content(file.filename, contents)
    if content_violation:
        ip = ids._client_ip(request)
        await ids.log_attack(db, ip=ip, attack_type="Invalid Income Proof",
                             endpoint="/api/kyc/income-proof", status="blocked",
                             user_id=user["id"], details=content_violation, severity="medium",
                             source="rule")
        # Secondary LLM review (optional, additive only): the rule engine has
        # already made the block decision above -- this only tries to explain
        # it better. If Ollama isn't running (e.g. in production), this
        # returns None and we fall back to the original static message
        # unchanged, so behavior is identical with or without it.
        llm_explanation = await llm_reviewer.explain_income_proof_rejection(extracted_text, content_violation)
        raise HTTPException(
            status_code=400,
            detail=llm_explanation or (
                "This doesn't look like a salary slip / income proof document. "
                "Please upload an actual payslip showing pay details (basic pay, HRA, deductions, net pay, etc.)."
            ),
        )

    # Best-effort: pull the actual salary figure printed on the slip, so a
    # loan application can be cross-checked against what the document says,
    # not just whether a document-shaped file was uploaded.
    extracted_salary = ids.extract_declared_salary_from_text(extracted_text)

    user_dir = UPLOADS_DIR / user["id"]
    user_dir.mkdir(parents=True, exist_ok=True)
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    stored_name = f"{uuid.uuid4()}{ext}"
    (user_dir / stored_name).write_bytes(contents)

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "income_proof_verified": True,
            "income_proof_filename": file.filename,
            "income_proof_uploaded_at": datetime.now(timezone.utc).isoformat(),
            "income_proof_extracted_salary": extracted_salary,
        }},
    )
    return {"ok": True, "verified": True, "filename": file.filename, "extracted_salary": extracted_salary}


@api.get("/kyc/income-proof/status")
async def income_proof_status(request: Request):
    user = await get_current_user(request, db)
    return {
        "required_above": INCOME_PROOF_REQUIRED_ABOVE,
        "verified": bool(user.get("income_proof_verified", False)),
        "filename": user.get("income_proof_filename"),
    }


# ============ Loans ============
@api.post("/loans/apply")
async def loans_apply(req: LoanApplyRequest, request: Request):
    user = await get_current_user(request, db)
    bank = await db.bank_verifications.find_one({"user_id": user["id"]}, {"_id": 0})
    if not bank:
        raise HTTPException(status_code=400, detail="Please connect your bank account first")

    income_proof_required = req.loan_amount >= INCOME_PROOF_REQUIRED_ABOVE
    if income_proof_required and not user.get("income_proof_verified", False):
        raise HTTPException(
            status_code=400,
            detail=(f"Loans of ₹{INCOME_PROOF_REQUIRED_ABOVE:,.0f} or more require a salary slip / "
                     "income proof upload before we can proceed. Please upload one and try again."),
        )

    kyc_flags = {
        "phone_verified": user.get("phone_verified", False),
        "pan_verified": user.get("pan_verified", False),
        "bank_verified": bank.get("bank_verified", False),
    }
    if income_proof_required:
        kyc_flags["income_proof_verified"] = user.get("income_proof_verified", False)

    result = score_loan(
        declared_monthly_income=req.monthly_salary,
        bank_monthly_income=bank["monthly_income"],
        avg_balance=bank["avg_balance"],
        employment_type=req.employment_type,
        loan_amount=req.loan_amount,
        existing_emi=req.existing_emi,
        tenure_months=req.tenure_months,
        kyc_flags=kyc_flags,
        slip_monthly_income=user.get("income_proof_extracted_salary"),
    )
    loan_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user["full_name"],
        "loan_amount": req.loan_amount,
        "employment_type": req.employment_type,
        "monthly_salary": req.monthly_salary,
        "tenure_months": req.tenure_months,
        "purpose": req.purpose,
        "eligibility_score": result["eligibility_score"],
        "risk_level": result["risk_level"],
        "loan_status": result["decision"],
        "suggested_amount": result["suggested_amount"],
        "factors": result["factors"],
        "risk_override_reason": result["risk_override_reason"],
        "estimated_emi": result["estimated_emi"],
        "interest_rate": result["interest_rate"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.loan_applications.insert_one(loan_doc)
    loan_doc.pop("_id", None)

    sanction_email_status = None
    if loan_doc["loan_status"] == "Approved":
        try:
            pdf_bytes = generate_sanction_letter(loan_doc=loan_doc, user=user)
            body = (
                f"Dear {user['full_name']},\n\n"
                f"Your SecureLend loan application has been approved. Please find your sanction "
                f"letter attached, with full terms and your EMI schedule.\n\n"
                f"Sanctioned amount: Rs.{loan_doc['loan_amount']:,.0f}\n"
                f"Tenure: {loan_doc['tenure_months']} months\n"
                f"Interest rate: {loan_doc['interest_rate']*100:.2f}% p.a.\n"
                f"Estimated EMI: Rs.{loan_doc['estimated_emi']:,.0f}/month\n\n"
                f"- SecureLend (simulated academic project, not a real financial instrument)"
            )
            sent = send_real_email(
                to_email=user["email"], subject="Your SecureLend loan has been approved",
                body_text=body, attachment_bytes=pdf_bytes,
                attachment_filename=f"SecureLend_Sanction_{loan_doc['id'][:8]}.pdf",
            )
            sanction_email_status = "sent" if sent else "demo_mode_not_sent"
            if not sent:
                logger.info(f"[Email demo mode] Sanction letter for {user['email']} generated "
                            f"({len(pdf_bytes)} bytes) but not emailed -- SMTP not configured.")
        except Exception as e:
            logger.warning(f"Failed to generate/send sanction letter: {e}")
            sanction_email_status = "error"
    loan_doc["sanction_email_status"] = sanction_email_status

    return loan_doc


@api.get("/loans/me")
async def my_loans(request: Request):
    user = await get_current_user(request, db)
    docs = await db.loan_applications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return docs


# ============ KYC file upload (with malicious upload detection) ============
@api.post("/upload/kyc")
async def upload_kyc(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request, db)
    contents = await file.read()
    size = len(contents)
    violation = ids.check_upload(file.filename, size)
    if violation:
        ip = ids._client_ip(request)
        await ids.log_attack(db, ip=ip, attack_type="Malicious File Upload",
                             endpoint="/api/upload/kyc", status="blocked",
                             user_id=user["id"], details=violation, severity="high",
                             source="rule")
        raise HTTPException(status_code=400, detail=f"Upload rejected: {violation}")
    return {"ok": True, "filename": file.filename, "size": size, "message": "File accepted (mock storage)"}


# ============ Public security transparency (no raw entities exposed) ============
# Unlike /admin/* (which needs an admin login and shows raw IPs/attack details),
# this is meant to be shown to any visitor: real-time-ish counts and categories
# only. No IP addresses, emails, user IDs, or request payloads are returned here.
@api.get("/security/overview")
async def security_overview():
    now = datetime.now(timezone.utc)
    last_24h = (now - timedelta(hours=24)).isoformat()
    last_1h = (now - timedelta(hours=1)).isoformat()

    attacks_24h = await db.attack_logs.count_documents({"timestamp": {"$gte": last_24h}})
    attacks_1h = await db.attack_logs.count_documents({"timestamp": {"$gte": last_1h}})
    currently_blocked = await db.blocked_ips.count_documents({"unblocked_at": None})

    pipeline = [
        {"$match": {"timestamp": {"$gte": last_24h}}},
        {"$group": {"_id": "$attack_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_type = [{"type": d["_id"], "count": d["count"]} async for d in db.attack_logs.aggregate(pipeline)]

    source_pipeline = [
        {"$match": {"timestamp": {"$gte": last_24h}}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]
    by_source = {d["_id"]: d["count"] async for d in db.attack_logs.aggregate(source_pipeline)}

    ml_loaded = ids.load_ml_scorer() is not None

    return {
        "generated_at": now.isoformat(),
        "attacks_detected_last_hour": attacks_1h,
        "attacks_detected_last_24h": attacks_24h,
        "ips_currently_blocked": currently_blocked,
        "attack_types_last_24h": by_type,
        "detected_by_rule_engine": by_source.get("rule", 0),
        "detected_by_ml_model": by_source.get("ml", 0),
        "ml_model_active": ml_loaded,
        "protections_active": [
            "SQL injection pattern detection",
            "XSS pattern detection",
            "Rate limiting (60 req/min flagged, 120 req/min blocked)",
            "Brute-force login detection (5 failures / 5 min)",
            "Daily login lockout (3 failures / 24h)",
            "Malicious file upload blocking",
            "Statistical anomaly detection (IsolationForest)",
            "Unauthorized admin-route access detection",
        ],
        "note": "Aggregated counts only. No IP addresses, emails, or individual request details are exposed on this public endpoint.",
    }


# ============ Bank Assistant (rule-based FAQ; swap-in point for a real LLM) ============
from assistant import get_bot_reply

class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@api.post("/assistant/ask")
async def assistant_ask(req: AssistantAskRequest, request: Request):
    ip = ids._client_ip(request)
    violation = ids.scan_payload_for_sqli(req.question) or ids.scan_payload_for_xss(req.question)
    if violation:
        await ids.log_attack(db, ip=ip, attack_type="Malicious Input (Assistant)",
                             endpoint="/api/assistant/ask", status="blocked",
                             details=violation, severity="high", source="rule")
        raise HTTPException(status_code=400, detail="Your message couldn't be processed.")
    answer, matched = await get_bot_reply(req.question)
    return {"answer": answer, "matched_topic": matched}


# ============ Admin: Stats / Attacks / IPs / Users / Loans / Demo ============
@api.get("/admin/stats")
async def admin_stats(request: Request):
    await require_admin(request, db)
    now = datetime.now(timezone.utc)
    today_iso = (now - timedelta(hours=24)).isoformat()

    total_attacks = await db.attack_logs.count_documents({})
    today_attacks = await db.attack_logs.count_documents({"timestamp": {"$gte": today_iso}})
    blocked_ips = await db.blocked_ips.count_documents({"unblocked_at": None})
    total_users = await db.users.count_documents({"role": "user"})
    total_loans = await db.loan_applications.count_documents({})
    approved = await db.loan_applications.count_documents({"loan_status": "Approved"})

    # by type
    pipeline = [{"$group": {"_id": "$attack_type", "count": {"$sum": 1}}}]
    by_type = [{"type": d["_id"], "count": d["count"]} async for d in db.attack_logs.aggregate(pipeline)]

    # last 7 days grouped by day
    seven = (now - timedelta(days=7))
    by_day = {}
    async for d in db.attack_logs.find({"timestamp": {"$gte": seven.isoformat()}}, {"timestamp": 1, "_id": 0}):
        day = d["timestamp"][:10]
        by_day[day] = by_day.get(day, 0) + 1
    timeline = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        timeline.append({"date": day, "count": by_day.get(day, 0)})

    return {
        "total_attacks": total_attacks,
        "today_attacks": today_attacks,
        "blocked_ips": blocked_ips,
        "total_users": total_users,
        "total_loans": total_loans,
        "approved_loans": approved,
        "by_type": by_type,
        "timeline": timeline,
    }


@api.get("/admin/attacks")
async def admin_attacks(request: Request, limit: int = 100):
    await require_admin(request, db)
    docs = await db.attack_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs


@api.get("/admin/ml/health")
async def admin_ml_health(request: Request):
    """Metadata & health of the trained IDS ML bundle."""
    await require_admin(request, db)
    import json as _json
    from pathlib import Path as _P
    scorer_loaded = ids.load_ml_scorer() is not None
    card_path = _P(__file__).parent / "ml" / "model_card.json"
    card = {}
    if card_path.exists():
        try:
            card = _json.loads(card_path.read_text())
        except Exception:
            card = {}
    return {
        "model_loaded": scorer_loaded,
        "artifacts": {
            "attack_classifier": "RandomForest",
            "anomaly_detector": "IsolationForest",
            "scaler": "StandardScaler",
            "label_encoder": True,
        },
        "features_in_order": card.get("features_in_order", []),
        "classes_in_order": card.get("classes_in_order", []),
        "anomaly_threshold": card.get("anomaly_threshold"),
        "training_rows": card.get("training_rows"),
        "test_rows": card.get("test_rows"),
        "attack_recall_at_threshold": card.get("attack_recall_at_threshold"),
        "false_positive_rate_at_threshold": card.get("false_positive_rate_at_threshold"),
    }


@api.get("/admin/blocked-ips")
async def admin_blocked_ips(request: Request):
    await require_admin(request, db)
    docs = await db.blocked_ips.find({"unblocked_at": None}, {"_id": 0}).sort("blocked_at", -1).to_list(100)
    return docs


@api.post("/admin/blocked-ips/{ip}/unblock")
async def admin_unblock_ip(ip: str, request: Request):
    await require_admin(request, db)
    await db.blocked_ips.update_many(
        {"ip_address": ip, "unblocked_at": None},
        {"$set": {"unblocked_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "ip": ip}


@api.get("/admin/users")
async def admin_users(request: Request):
    await require_admin(request, db)
    docs = await db.users.find({"role": "user"}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(200)
    # mask PAN
    for d in docs:
        if d.get("pan"):
            d["pan"] = d["pan"][:2] + "XXXX" + d["pan"][-2:]
    return docs


@api.get("/admin/loans")
async def admin_loans(request: Request):
    await require_admin(request, db)
    docs = await db.loan_applications.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@api.post("/admin/loans/{loan_id}/override")
async def admin_override_loan(loan_id: str, request: Request):
    await require_admin(request, db)
    body = await request.json()
    new_status = body.get("status")
    if new_status not in ("Approved", "Rejected", "Manual Review"):
        raise HTTPException(status_code=400, detail="Invalid status")
    r = await db.loan_applications.update_one(
        {"id": loan_id}, {"$set": {"loan_status": new_status, "overridden": True}}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Loan not found")
    return {"ok": True}


# ============ Admin: Demo attack simulator ============
DEMO_ATTACKS = {
    "sql_injection": {
        "attack_type": "SQL Injection",
        "endpoint": "/api/auth/login",
        "severity": "critical",
        "details": "Payload: ' OR '1'='1' --",
        "features": {
            "requests_per_minute": 8, "failed_logins_5min": 1,
            "contains_sql_keywords": 1, "contains_script_tag": 0,
            "endpoint_sensitivity": 0, "role_mismatch": 0, "file_ext_risk": 0,
            "payload_size_kb": 0.35, "unique_endpoints_1min": 2,
        },
    },
    "brute_force": {
        "attack_type": "Brute Force Login",
        "endpoint": "/api/auth/login",
        "severity": "high",
        "details": "10 failed login attempts in 60s from same IP",
        "features": {
            "requests_per_minute": 42, "failed_logins_5min": 18,
            "contains_sql_keywords": 0, "contains_script_tag": 0,
            "endpoint_sensitivity": 0, "role_mismatch": 0, "file_ext_risk": 0,
            "payload_size_kb": 0.2, "unique_endpoints_1min": 1,
        },
    },
    "bot_flood": {
        "attack_type": "Bot Flood",
        "endpoint": "/api/loans/apply",
        "severity": "high",
        "details": "150+ req/min – rate limit breached",
        "features": {
            "requests_per_minute": 170, "failed_logins_5min": 0,
            "contains_sql_keywords": 0, "contains_script_tag": 0,
            "endpoint_sensitivity": 1, "role_mismatch": 0, "file_ext_risk": 0,
            "payload_size_kb": 1.2, "unique_endpoints_1min": 3,
        },
    },
    "unauthorized_admin": {
        "attack_type": "Unauthorized Admin Access",
        "endpoint": "/api/admin/users",
        "severity": "high",
        "details": "Non-admin JWT attempted to hit /admin route",
        "features": {
            "requests_per_minute": 12, "failed_logins_5min": 0,
            "contains_sql_keywords": 0, "contains_script_tag": 0,
            "endpoint_sensitivity": 2, "role_mismatch": 1, "file_ext_risk": 0,
            "payload_size_kb": 0.1, "unique_endpoints_1min": 4,
        },
    },
    "malicious_upload": {
        "attack_type": "Malicious File Upload",
        "endpoint": "/api/upload/kyc",
        "severity": "high",
        "details": "Blocked file: kyc_document.exe (executable)",
        "features": {
            "requests_per_minute": 4, "failed_logins_5min": 0,
            "contains_sql_keywords": 0, "contains_script_tag": 0,
            "endpoint_sensitivity": 1, "role_mismatch": 0, "file_ext_risk": 1,
            "payload_size_kb": 320.0, "unique_endpoints_1min": 2,
        },
    },
    "xss": {
        "attack_type": "XSS Attempt",
        "endpoint": "/api/kyc/pan-check",
        "severity": "high",
        "details": "Payload: <script>alert(1)</script>",
        "features": {
            "requests_per_minute": 6, "failed_logins_5min": 0,
            "contains_sql_keywords": 0, "contains_script_tag": 1,
            "endpoint_sensitivity": 0, "role_mismatch": 0, "file_ext_risk": 0,
            "payload_size_kb": 0.4, "unique_endpoints_1min": 2,
        },
    },
}


@api.post("/admin/demo/attack")
async def admin_demo_attack(request: Request):
    await require_admin(request, db)
    body = await request.json()
    kind = body.get("kind")
    if kind not in DEMO_ATTACKS:
        raise HTTPException(status_code=400, detail=f"Unknown attack kind. Options: {list(DEMO_ATTACKS)}")
    import random
    fake_ip = f"{random.randint(45, 200)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    meta = DEMO_ATTACKS[kind]

    # 1) Rule engine log (existing behaviour)
    rule_log = await ids.log_attack(
        db, ip=fake_ip,
        attack_type=meta["attack_type"], endpoint=meta["endpoint"],
        status="blocked", severity=meta["severity"], details=meta["details"],
        source="rule",
    )

    # 2) Route the same synthetic event through the custom ML scorer
    ml_log = None
    ml_verdict = None
    scorer = ids.load_ml_scorer()
    if scorer is not None:
        try:
            from datetime import datetime as _dt, timezone as _tz
            features = {
                **meta["features"],
                "hour_of_day": _dt.now(_tz.utc).hour,
            }
            verdict = scorer(features)
            ml_verdict = {**verdict, "features": features}
            if verdict["action"] in ("block", "flag"):
                pretty = ids.ML_LABEL_TO_ATTACK.get(
                    verdict["predicted_type"], verdict["predicted_type"]
                )
                details = (
                    f"predicted={verdict['predicted_type']} "
                    f"conf={verdict['confidence']:.3f} "
                    f"anomaly={verdict['anomaly_score']:.3f} "
                    f"(thr={verdict['anomaly_threshold']:.3f})"
                )
                ml_log = await ids.log_attack(
                    db, ip=fake_ip, attack_type=pretty, endpoint=meta["endpoint"],
                    status="blocked" if verdict["action"] == "block" else "flagged",
                    severity=verdict["severity"], details=details, source="ml",
                )
        except Exception as e:
            import logging
            logging.getLogger("securelend").warning("Demo ML scoring failed: %s", e)

    # For brute force / bot flood also add to blocked_ips
    if kind in ("brute_force", "bot_flood"):
        await ids.block_ip(db, fake_ip, meta["attack_type"])

    rule_log.pop("_id", None)
    if ml_log:
        ml_log.pop("_id", None)
    return {
        "ok": True,
        "simulated_ip": fake_ip,
        "rule_log": rule_log,
        "ml_log": ml_log,
        "ml_verdict": ml_verdict,
        # Back-compat: keep original single `log` key pointing at the rule entry
        "log": rule_log,
    }


app.include_router(api)


# ============ Startup ============
@app.on_event("startup")
async def startup():
    # indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("phone")
    await db.users.create_index("pan")
    await db.loan_applications.create_index("user_id")
    await db.attack_logs.create_index([("timestamp", -1)])
    await db.blocked_ips.create_index("ip_address")
    # TTL index: documents auto-delete 25h after insertion (past the 24h daily
    # lockout window with headroom), so this collection self-cleans and never
    # grows unbounded -- no cron/manual cleanup job required.
    await db.login_failure_events.create_index("ts", expireAfterSeconds=25 * 60 * 60)
    await db.login_failure_events.create_index([("ip", 1), ("email", 1), ("ts", -1)])

    # ML baseline
    ids.train_baseline_model()
    # Warm up the trained custom IDS model bundle
    try:
        ids.load_ml_scorer()
        logger.info("Custom IDS ML model loaded (attack_classifier + anomaly_detector)")
    except Exception as e:
        logger.warning("Custom IDS model load failed: %s", e)

    # seed
    await seed_admin(db)
    await seed_demo_data(db)

    # write test credentials
    memory = Path(__file__).parent / "memory"
    memory.mkdir(exist_ok=True)
    (memory / "test_credentials.md").write_text(
        f"""# SecureLend Test Credentials

## Admin
- Email: `{os.environ['ADMIN_EMAIL']}`
- Password: `{os.environ['ADMIN_PASSWORD']}`
- Role: admin
- Access: All /api/admin/* endpoints & Admin Security Dashboard

## Demo User
- Email: `{os.environ['DEMO_USER_EMAIL']}`
- Password: `{os.environ['DEMO_USER_PASSWORD']}`
- Role: user

## Auth Endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me
"""
    )
    logger.info("SecureLend startup complete")


@app.on_event("shutdown")
async def shutdown():
    client.close()