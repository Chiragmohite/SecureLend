"""Backend API integration tests for SecureLend.

Covers: health, auth (admin+demo user), IDS (SQLi, brute-force, unauth admin),
OTP, registration, bank connect, loan apply, admin endpoints, demo attack sim.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://loan-guard-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@securelend.io"
ADMIN_PASSWORD = "Admin@1234"
DEMO_EMAIL = "rahul.sharma@example.com"
DEMO_PASSWORD = "Demo@1234"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(http):
    r = http.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def user_token(http):
    r = http.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


# ---------- Health ----------
class TestHealth:
    def test_health_ok(self, http):
        r = http.get(f"{API}/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "time" in data


# ---------- Auth ----------
class TestAuth:
    def test_admin_login(self, http):
        r = http.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 10
        assert data["user"]["role"] == "admin"
        assert data["user"]["email"] == ADMIN_EMAIL
        assert "password_hash" not in data["user"]

    def test_demo_user_login(self, http):
        r = http.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["role"] == "user"
        assert data["user"]["email"] == DEMO_EMAIL
        assert "password_hash" not in data["user"]

    def test_auth_me_returns_user(self, http, user_headers):
        r = http.get(f"{API}/auth/me", headers=user_headers)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == DEMO_EMAIL
        assert "password_hash" not in u

    def test_auth_me_unauthorized(self, http):
        # remove any session default headers
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------- IDS ----------
class TestIDS:
    def test_sql_injection_blocked(self, http):
        r = http.post(f"{API}/auth/login", json={"email": "a' OR '1'='1", "password": "x"})
        # SQLi middleware blocks before pydantic validation
        assert r.status_code == 400, r.text
        assert "malicious" in r.text.lower() or "blocked" in r.text.lower()

    def test_unauthorized_admin_blocked(self, http):
        r = requests.get(f"{API}/admin/users")
        assert r.status_code == 403
        detail = r.json().get("detail", "")
        assert "Admin" in detail or "admin" in detail

    def test_brute_force_lockout(self):
        """5+ failed logins from same IP for target email → 429 and blocked IP."""
        # Use a unique email that doesn't exist to avoid affecting real users
        target = f"bf_{uuid.uuid4().hex[:8]}@example.com"
        got_429 = False
        for i in range(8):
            r = requests.post(f"{API}/auth/login", json={"email": target, "password": "wrong"})
            if r.status_code == 429:
                got_429 = True
                break
            # 401 expected for early attempts; 403 if the IP got blocked as a result
            assert r.status_code in (401, 429, 403), f"attempt {i}: {r.status_code} {r.text}"
        assert got_429, "Expected 429 after 5+ failed logins"

        # cleanup: unblock the IP so subsequent tests aren't affected
        # get admin token via a fresh call (need admin session that itself isn't blocked)
        # After IP block, further calls from same IP would 403. Try to unblock via admin using same IP.
        admin_r = requests.post(
            f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if admin_r.status_code == 200:
            tok = admin_r.json()["token"]
            ips = requests.get(f"{API}/admin/blocked-ips", headers={"Authorization": f"Bearer {tok}"}).json()
            for ip_doc in ips:
                requests.post(
                    f"{API}/admin/blocked-ips/{ip_doc['ip_address']}/unblock",
                    headers={"Authorization": f"Bearer {tok}"},
                )
        else:
            # IP itself blocked → we can still call unblock w/ admin cookie? Not possible.
            # Log a warning-style assert so test still passes if 429 was hit.
            pass


# ---------- OTP ----------
class TestOTP:
    def test_otp_send_and_verify(self, http):
        phone = f"9{uuid.uuid4().int % 1000000000:09d}"
        # must start with 6-9
        phone = "9" + phone[1:]
        r = http.post(f"{API}/otp/send", json={"phone": phone})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sent"] is True
        otp = data.get("demo_otp")
        assert otp and len(otp) == 6

        r2 = http.post(f"{API}/otp/verify", json={"phone": phone, "otp": otp})
        assert r2.status_code == 200, r2.text
        assert r2.json()["verified"] is True

    def test_otp_invalid_phone(self, http):
        r = http.post(f"{API}/otp/send", json={"phone": "123"})
        assert r.status_code == 400


# ---------- Registration ----------
class TestRegistration:
    def test_register_valid_and_invalid_pan(self, http):
        suffix = uuid.uuid4().hex[:6].upper()
        # invalid PAN
        r_bad = http.post(f"{API}/auth/register", json={
            "full_name": "Test User",
            "email": f"testuser_{suffix}@example.com",
            "password": "Test@1234",
            "dob": "1995-01-01",
            "phone": "9" + str(uuid.uuid4().int)[-9:],
            "pan": "INVALIDPAN"
        })
        assert r_bad.status_code == 422, r_bad.text

        # valid register
        phone = "9" + str(uuid.uuid4().int)[-9:]
        pan = "ABCDE" + str(uuid.uuid4().int)[-4:] + "F"
        r = http.post(f"{API}/auth/register", json={
            "full_name": "Test User",
            "email": f"testuser_{suffix}@example.com",
            "password": "Test@1234",
            "dob": "1995-01-01",
            "phone": phone,
            "pan": pan,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data
        assert data["user"]["role"] == "user"
        assert "password_hash" not in data["user"]


# ---------- Bank Connect ----------
class TestBankConnect:
    def test_bank_requires_consent(self, http, user_headers):
        r = http.post(f"{API}/bank/connect",
                      json={"bank_name": "HDFC", "consent": False},
                      headers=user_headers)
        assert r.status_code == 400
        assert "consent" in r.json()["detail"].lower()

    def test_bank_connect_with_consent(self, http, user_headers):
        r = http.post(f"{API}/bank/connect",
                      json={"bank_name": "HDFC", "consent": True},
                      headers=user_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["bank_name"] == "HDFC"
        assert d["bank_verified"] is True
        assert d["monthly_income"] > 0
        assert d["avg_balance"] > 0

    def test_bank_unknown_bank_rejected(self, http, user_headers):
        r = http.post(f"{API}/bank/connect",
                      json={"bank_name": "FakeBank", "consent": True},
                      headers=user_headers)
        assert r.status_code == 400


# ---------- Loan Apply ----------
class TestLoans:
    def test_loan_apply_returns_explainable(self, http, user_headers):
        # ensure bank is connected first
        http.post(f"{API}/bank/connect",
                  json={"bank_name": "HDFC", "consent": True}, headers=user_headers)

        r = http.post(f"{API}/loans/apply", json={
            "loan_amount": 300000,
            "employment_type": "salaried",
            "monthly_salary": 75000,
            "existing_emi": 5000,
            "purpose": "Home Renovation",
        }, headers=user_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "eligibility_score" in d
        assert d["risk_level"] in ("LOW", "MEDIUM", "HIGH")
        assert d["loan_status"] in ("Approved", "Manual Review", "Rejected")
        # 6 factors now: the new scoring engine adds "Income Consistency"
        # (declared vs bank-observed income) as a real underwriting check.
        assert isinstance(d["factors"], list) and len(d["factors"]) == 6
        # each factor should have name/weight/score/detail
        for f in d["factors"]:
            for k in ("name", "weight", "score", "detail"):
                assert k in f


# ---------- Admin Endpoints ----------
class TestAdmin:
    def test_admin_stats(self, http, admin_headers):
        r = http.get(f"{API}/admin/stats", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_attacks", "today_attacks", "blocked_ips",
                  "total_users", "total_loans", "by_type", "timeline"):
            assert k in d
        assert isinstance(d["by_type"], list)
        assert isinstance(d["timeline"], list)
        assert len(d["timeline"]) == 7

    def test_admin_attacks(self, http, admin_headers):
        r = http.get(f"{API}/admin/attacks?limit=100", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_blocked_ips(self, http, admin_headers):
        r = http.get(f"{API}/admin/blocked-ips", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_users(self, http, admin_headers):
        r = http.get(f"{API}/admin/users", headers=admin_headers)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        # PAN should be masked
        for u in users:
            if u.get("pan"):
                assert "XXXX" in u["pan"]

    def test_admin_demo_attack_simulator(self, http, admin_headers):
        kinds = ["sql_injection", "brute_force", "bot_flood",
                 "unauthorized_admin", "malicious_upload", "xss"]
        for kind in kinds:
            r = http.post(f"{API}/admin/demo/attack", json={"kind": kind}, headers=admin_headers)
            assert r.status_code == 200, f"{kind}: {r.text}"
            d = r.json()
            assert d["ok"] is True
            assert "simulated_ip" in d
            assert d["log"]["attack_type"]

    def test_admin_loan_override(self, http, admin_headers):
        # find a loan
        loans_r = http.get(f"{API}/admin/loans", headers=admin_headers)
        assert loans_r.status_code == 200
        loans = loans_r.json()
        if not loans:
            pytest.skip("No loans to override")
        lid = loans[0]["id"]
        r = http.post(f"{API}/admin/loans/{lid}/override",
                      json={"status": "Approved"}, headers=admin_headers)
        assert r.status_code == 200, r.text
        # verify
        loans_r2 = http.get(f"{API}/admin/loans", headers=admin_headers)
        item = next((x for x in loans_r2.json() if x["id"] == lid), None)
        assert item is not None
        assert item["loan_status"] == "Approved"


# ---------- Cleanup ----------
@pytest.fixture(scope="session", autouse=True)
def _final_cleanup(request):
    yield
    # unblock any test-blocked IPs
    try:
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if r.status_code == 200:
            tok = r.json()["token"]
            ips = requests.get(f"{API}/admin/blocked-ips",
                               headers={"Authorization": f"Bearer {tok}"}).json()
            for ip_doc in ips:
                requests.post(
                    f"{API}/admin/blocked-ips/{ip_doc['ip_address']}/unblock",
                    headers={"Authorization": f"Bearer {tok}"},
                )
    except Exception:
        pass