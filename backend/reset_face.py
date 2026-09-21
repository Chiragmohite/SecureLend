"""
reset_face.py
-------------
Fixes "This face appears to already be linked to another registered account"
while testing. Registration compares your new face against the face data
stored on every existing user, so an earlier test signup with the same face
will block new ones.

Run from the backend folder with the venv activated:

    python reset_face.py                 # list users that have face data
    python reset_face.py you@email.com   # remove face data for that user
    python reset_face.py --delete you@email.com   # delete that user entirely

The account's email/password are untouched unless you use --delete.
"""
import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

args = sys.argv[1:]

if not args:
    users = list(db.users.find(
        {"face_embedding": {"$exists": True, "$ne": None}},
        {"email": 1, "full_name": 1, "role": 1, "created_at": 1},
    ))
    if not users:
        print("No users have face data stored.")
    for u in users:
        print(f"{u.get('email')}  |  {u.get('full_name')}  |  {u.get('role')}  |  {u.get('created_at')}")
    print(f"\n{len(users)} user(s) with face data.")
elif args[0] == "--delete" and len(args) == 2:
    user = db.users.find_one({"email": args[1]})
    if not user:
        print(f"No user found with email: {args[1]}")
    else:
        db.users.delete_one({"email": args[1]})
        db.loan_applications.delete_many({"user_id": user["id"]})
        db.bank_verifications.delete_many({"user_id": user["id"]})
        print(f"Deleted user {args[1]} and their loans/bank records.")
else:
    email = args[0]
    result = db.users.update_one({"email": email}, {"$unset": {"face_embedding": ""}})
    if result.matched_count == 0:
        print(f"No user found with email: {email}")
    else:
        print(f"Face data removed for {email}. You can register with that face again.")