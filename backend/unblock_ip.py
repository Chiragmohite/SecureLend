import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# >>> EDIT if testing against a non-default IP <<<
TARGET_IP = "127.0.0.1"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

result = db.blocked_ips.update_many(
    {"ip_address": TARGET_IP, "unblocked_at": None},
    {"$set": {"unblocked_at": datetime.now(timezone.utc).isoformat()}}
)
print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")
print("IP unblocked." if result.modified_count else "No active block found for this IP.")