"""
reset_mislabeled.py
--------------------
Resets specific ml_inference_log entries back to unlabeled (true_label=None)
so they can be relabeled correctly. Use this to undo mistaken labels.

Run from backend/ with your venv active:
    python reset_mislabeled.py
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def reset_all_labels():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    result = await db.ml_inference_log.update_many(
        {"true_label": {"$ne": None}},
        {"$set": {"true_label": None}},
    )
    print(f"Reset {result.modified_count} labeled entries back to unlabeled.")
    print("Run 'python validate_against_real_traffic.py --label' again to redo them carefully.")
    client.close()


if __name__ == "__main__":
    asyncio.run(reset_all_labels())