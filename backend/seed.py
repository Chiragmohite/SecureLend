"""Seed demo users, loans and attack logs so the dashboards look alive."""
import os
import uuid
import random
from datetime import datetime, timezone, timedelta

from auth import hash_password


DEMO_NAMES = [
    ("Rahul Sharma", "rahul.sharma@example.com", "9876543210", "ABCDE1234F"),
    ("Priya Patel", "priya.patel@example.com", "9812345678", "PQRST5678G"),
    ("Amit Kumar", "amit.kumar@example.com", "9898989898", "LMNOP2345H"),
    ("Sneha Verma", "sneha.verma@example.com", "9765432101", "XYZAB6789J"),
    ("Vikram Singh", "vikram.singh@example.com", "9887766554", "MNOPQ4321K"),
    ("Kavya Iyer", "kavya.iyer@example.com", "9776655443", "FGHIJ9876L"),
    ("Rohit Mehta", "rohit.mehta@example.com", "9665544332", "STUVW3210M"),
    ("Ananya Rao", "ananya.rao@example.com", "9554433221", "KLMNO7654P"),
    ("Karan Gupta", "karan.gupta@example.com", "9443322110", "BCDEF1122Q"),
    ("Ishita Joshi", "ishita.joshi@example.com", "9332211009", "GHIJK3344R"),
]

BANKS = ["SBI", "HDFC", "ICICI", "Axis"]
PURPOSES = ["Home Renovation", "Education", "Medical", "Wedding", "Business Expansion", "Debt Consolidation"]
EMPLOYMENTS = ["salaried", "self_employed", "business"]


async def seed_admin(db):
    email = os.environ["ADMIN_EMAIL"]
    pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    now = datetime.now(timezone.utc).isoformat()
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(pw),
            "full_name": "SecureLend Admin",
            "phone": "9000000000",
            "phone_verified": True,
            "pan": "ADMIN0000A",
            "pan_verified": True,
            "dob": "1990-01-01",
            "role": "admin",
            "created_at": now,
        })
    else:
        from auth import verify_password
        if not verify_password(pw, existing["password_hash"]):
            await db.users.update_one(
                {"email": email},
                {"$set": {"password_hash": hash_password(pw)}}
            )


async def seed_demo_data(db):
    """Only seed if demo users don't exist."""
    demo_email = os.environ["DEMO_USER_EMAIL"]
    if await db.users.find_one({"email": demo_email}):
        return

    now = datetime.now(timezone.utc)
    demo_pw_hash = hash_password(os.environ["DEMO_USER_PASSWORD"])

    user_ids = []
    for i, (name, email, phone, pan) in enumerate(DEMO_NAMES):
        uid = str(uuid.uuid4())
        user_ids.append((uid, name, email))
        await db.users.insert_one({
            "id": uid,
            "email": email,
            "password_hash": demo_pw_hash,
            "full_name": name,
            "phone": phone,
            "phone_verified": True,
            "pan": pan,
            "pan_verified": True,
            "dob": f"199{i % 10}-0{(i % 9) + 1}-1{(i % 9)}",
            "role": "user",
            "created_at": (now - timedelta(days=random.randint(1, 60))).isoformat(),
        })
        # bank verification
        income = random.choice([45000, 62000, 85000, 120000, 55000, 95000])
        await db.bank_verifications.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "bank_name": random.choice(BANKS),
            "account_masked": f"XXXX-XXXX-{random.randint(1000, 9999)}",
            "monthly_income": income,
            "avg_balance": income * random.uniform(0.4, 2.2),
            "bank_verified": True,
            "consent_given_at": (now - timedelta(days=random.randint(1, 30))).isoformat(),
        })

    # Loans
    for uid, name, email in user_ids[:8]:
        amount = random.choice([50000, 150000, 300000, 500000, 750000, 100000])
        score = round(random.uniform(35, 92), 1)
        if score >= 70:
            status = "Approved"
            risk = "LOW"
        elif score >= 50:
            status = "Manual Review"
            risk = "MEDIUM"
        else:
            status = "Rejected"
            risk = "HIGH"
        await db.loan_applications.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "user_name": name,
            "loan_amount": amount,
            "employment_type": random.choice(EMPLOYMENTS),
            "monthly_salary": random.randint(45000, 130000),
            "purpose": random.choice(PURPOSES),
            "eligibility_score": score,
            "risk_level": risk,
            "loan_status": status,
            "factors": [],
            "created_at": (now - timedelta(days=random.randint(0, 20))).isoformat(),
            "decided_at": (now - timedelta(days=random.randint(0, 20))).isoformat(),
        })

    # Attack logs (about 50 spread over last 7 days)
    attack_types = [
        ("SQL Injection", "critical", "blocked"),
        ("Brute Force Login", "high", "blocked"),
        ("Bot Flood", "high", "blocked"),
        ("Unauthorized Admin Access", "high", "blocked"),
        ("Malicious File Upload", "medium", "blocked"),
        ("Rate Limit Exceeded", "medium", "flagged"),
        ("Anomalous Traffic", "medium", "flagged"),
        ("XSS Attempt", "high", "blocked"),
    ]
    endpoints = [
        "/api/auth/login", "/api/loans/apply", "/api/admin/users",
        "/api/kyc/pan", "/api/bank/connect", "/api/upload/kyc",
    ]
    for i in range(50):
        atk, sev, st = random.choice(attack_types)
        ts = now - timedelta(hours=random.randint(0, 168), minutes=random.randint(0, 59))
        await db.attack_logs.insert_one({
            "id": str(uuid.uuid4()),
            "ip_address": f"{random.randint(10,240)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            "attack_type": atk,
            "endpoint": random.choice(endpoints),
            "user_id": None,
            "timestamp": ts.isoformat(),
            "status": st,
            "severity": sev,
            "details": f"Detected via {'rule engine' if random.random() > 0.4 else 'anomaly detector'}",
        })

    # Blocked IPs sample
    for _ in range(3):
        ip = f"{random.randint(10,240)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        await db.blocked_ips.insert_one({
            "id": str(uuid.uuid4()),
            "ip_address": ip,
            "reason": random.choice(["Brute Force Login", "SQL Injection", "Bot Flood"]),
            "blocked_at": (now - timedelta(hours=random.randint(0, 24))).isoformat(),
            "expires_at": (now.timestamp() + 900),
            "unblocked_at": None,
        })
