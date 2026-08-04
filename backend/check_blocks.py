import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

active = list(db.blocked_ips.find({"unblocked_at": None}))
print(f"Active blocks: {len(active)}")
for b in active:
    print(f" - ip={b.get('ip_address')} reason={b.get('reason')} blocked_at={b.get('blocked_at')}")