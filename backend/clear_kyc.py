"""
One-off script to reset KYC verification state for a single user,
so you can re-test the OTP -> PAN -> bank -> income-proof flow from scratch.
Does NOT delete the user account, email, or password.

Run from the backend folder with the venv activated:
    python clear_kyc.py
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# >>> EDIT THIS to your test account's email <<<
TARGET_EMAIL = "chiragmohite02@gmail.com"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

user = db.users.find_one({"email": TARGET_EMAIL})
if not user:
    print(f"No user found with email: {TARGET_EMAIL}")
else:
    result = db.users.update_one(
        {"email": TARGET_EMAIL},
        {"$unset": {
            "phone_verified": "",
            "pan_verified": "",
            "bank_verified": "",
            "income_proof_verified": "",
            "income_proof_filename": "",
            "income_proof_uploaded_at": "",
        }}
    )
    bank_result = db.bank_verifications.delete_many({"user_id": user["id"]})

    print(f"User matched: {result.matched_count}, modified: {result.modified_count}")
    print(f"Bank verification records deleted: {bank_result.deleted_count}")
    print("Done — KYC state reset. Account/login unchanged.")