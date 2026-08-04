import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

users = list(db.users.find({}, {"email": 1, "_id": 0}))
print(f"Found {len(users)} user(s):")
for u in users:
    print(" -", u.get("email"))