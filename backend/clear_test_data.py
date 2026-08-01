"""
clear_test_data.py
-------------------
Clears registered/test data from the SecureLend MongoDB database.

Run from the backend/ folder (so it can find .env), with your venv active:
    python clear_test_data.py

By default this clears EVERYTHING in all 5 collections, including your
seeded admin/demo users. If you want to keep the admin account and only
wipe real user signups + their data, set KEEP_ADMIN = True below.
"""

import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Set to True to keep the admin user (role == "admin") and only wipe
# regular user accounts + their related data. Set False to wipe everything.
KEEP_ADMIN = False


async def clear():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    if KEEP_ADMIN:
        # Find non-admin user ids first, so we can also clean up their
        # related loan/bank records specifically.
        user_ids = [u["id"] async for u in db.users.find({"role": {"$ne": "admin"}}, {"id": 1})]

        users_result = await db.users.delete_many({"role": {"$ne": "admin"}})
        loans_result = await db.loan_applications.delete_many({"user_id": {"$in": user_ids}})
        bank_result = await db.bank_verifications.delete_many({"user_id": {"$in": user_ids}})

        print(f"users deleted:              {users_result.deleted_count} (admin kept)")
        print(f"loan_applications deleted:  {loans_result.deleted_count}")
        print(f"bank_verifications deleted: {bank_result.deleted_count}")
        print("attack_logs / blocked_ips left untouched (not user-specific)")
    else:
        users_result = await db.users.delete_many({})
        loans_result = await db.loan_applications.delete_many({})
        bank_result = await db.bank_verifications.delete_many({})
        attacks_result = await db.attack_logs.delete_many({})
        blocked_result = await db.blocked_ips.delete_many({})

        print(f"users deleted:              {users_result.deleted_count}")
        print(f"loan_applications deleted:  {loans_result.deleted_count}")
        print(f"bank_verifications deleted: {bank_result.deleted_count}")
        print(f"attack_logs deleted:        {attacks_result.deleted_count}")
        print(f"blocked_ips deleted:        {blocked_result.deleted_count}")

    client.close()
    print("\nDone. Re-run seed.py if you need admin/demo accounts back.")


if __name__ == "__main__":
    confirm = input(
        "This will permanently delete data from the LIVE Atlas database. "
        "Type 'yes' to continue: "
    )
    if confirm.strip().lower() == "yes":
        asyncio.run(clear())
    else:
        print("Cancelled.")