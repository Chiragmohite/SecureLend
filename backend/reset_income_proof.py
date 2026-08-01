"""
reset_income_proof.py
----------------------
Resets the income-proof verification flag for one user, so the next
loan application above the required threshold will prompt for a fresh
salary slip upload again (useful for re-testing that flow).

Run from backend/ with your venv active:
    python reset_income_proof.py your_email@example.com
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def reset(email: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    result = await db.users.update_one(
        {"email": email.lower()},
        {"$set": {
            "income_proof_verified": False,
            "income_proof_filename": None,
            "income_proof_extracted_salary": None,
        }},
    )
    if result.matched_count == 0:
        print(f"No user found with email: {email}")
    else:
        print(f"Reset income proof status for {email}. "
              f"Next loan >= the required threshold will ask for a fresh upload.")

    client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python reset_income_proof.py your_email@example.com")
        sys.exit(1)
    asyncio.run(reset(sys.argv[1]))