"""
unblock_my_ip.py
-----------------
Directly unblocks an IP in the database, bypassing the API entirely.
Needed because the API's own unblock endpoint is itself behind the
IDS middleware's IP-block check -- an admin whose IP got blocked can't
use the UI's "Unblock" button to fix that (chicken-and-egg lockout).

Run from backend/ with your venv active:
    python unblock_my_ip.py 127.0.0.1
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def unblock(ip: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    result = await db.blocked_ips.update_many(
        {"ip_address": ip, "unblocked_at": None},
        {"$set": {"unblocked_at": datetime.now(timezone.utc).isoformat()}},
    )
    print(f"Unblocked {result.modified_count} active block(s) for IP: {ip}")
    client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python unblock_my_ip.py <ip_address>")
        print("For local testing, this is usually: python unblock_my_ip.py 127.0.0.1")
        sys.exit(1)
    asyncio.run(unblock(sys.argv[1]))