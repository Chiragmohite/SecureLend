"""
validate_against_real_traffic.py
----------------------------------
Evaluates the trained IDS model against REAL traffic your app has
actually processed (captured via ids.log_ml_inference into the
`ml_inference_log` collection) -- as opposed to train_ids_model.py's
synthetic data. This is the genuine "test IDS against real data" step:
train on custom-generated synthetic data, VALIDATE against real captured
requests.

Two ways to use this:

1. LABELING MODE (run this first, once, after generating some real
   traffic): interactively review captured requests and tag each one
   with what it actually was (a real attack you sent on purpose, or
   genuine normal use). This builds ground truth -- without it, there's
   nothing to score accuracy against, just predictions with no reference.

       python validate_against_real_traffic.py --label

2. EVALUATE MODE (run after labeling some data): scores the model's
   predictions against your labeled ground truth and prints a real
   accuracy/precision/recall report -- on live traffic, not synthetic.

       python validate_against_real_traffic.py --evaluate

Run from backend/ with your venv active (needs MONGO_URL from .env).
"""
import argparse
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml"))

load_dotenv()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

VALID_LABELS = [
    "normal", "sql_injection", "xss_attempt", "brute_force_login",
    "bot_flood", "malicious_upload", "unauthorized_admin", "anomalous_traffic",
]


async def label_mode():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    unlabeled = await db.ml_inference_log.find({"true_label": None}).sort("timestamp", -1).to_list(200)
    if not unlabeled:
        print("No unlabeled entries found. Generate some real traffic first "
              "(register accounts, apply for loans, and re-run your earlier "
              "SQLi/XSS/rate-limit/brute-force tests -- they'll now get captured).")
        client.close()
        return

    print(f"Found {len(unlabeled)} unlabeled real requests.\n")
    print("For each one, tell me what it actually was. Options:")
    for i, lbl in enumerate(VALID_LABELS):
        print(f"  {i}: {lbl}")
    print("  s: skip this one")
    print("  q: quit and save progress\n")

    labeled_count = 0
    for doc in unlabeled:
        print("-" * 60)
        print(f"Endpoint: {doc['endpoint']}")
        print(f"IP: {doc['ip_address']}   Time: {doc['timestamp']}")
        print(f"Features: {doc['features']}")
        print(f"Model predicted: {doc['predicted_type']}  (action: {doc['action']})")
        choice = input("What was this really? > ").strip().lower()

        if choice == "q":
            break
        if choice == "s":
            continue
        try:
            idx = int(choice)
            true_label = VALID_LABELS[idx]
        except (ValueError, IndexError):
            print("Not a valid option, skipping.")
            continue

        await db.ml_inference_log.update_one({"id": doc["id"]}, {"$set": {"true_label": true_label}})
        labeled_count += 1

    print(f"\nLabeled {labeled_count} entries this session.")
    client.close()


async def evaluate_mode():
    from sklearn.metrics import classification_report, confusion_matrix
    import numpy as np

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    labeled = await db.ml_inference_log.find({"true_label": {"$ne": None}}).to_list(1000)
    if len(labeled) < 5:
        print(f"Only {len(labeled)} labeled real samples found -- too few for a "
              "meaningful report. Run --label mode first and label more.")
        client.close()
        return

    y_true = [d["true_label"] for d in labeled]
    y_pred = [d["predicted_type"] if d["predicted_type"] else "normal" for d in labeled]

    print(f"Evaluating on {len(labeled)} REAL labeled requests (not synthetic).\n")
    print(classification_report(y_true, y_pred, zero_division=0))

    labels_present = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels_present)
    print(f"\nConfusion matrix (labels: {labels_present}):")
    print(cm)

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--label", action="store_true", help="Interactively label captured real traffic")
    group.add_argument("--evaluate", action="store_true", help="Evaluate model against labeled real traffic")
    args = parser.parse_args()

    if args.label:
        asyncio.run(label_mode())
    else:
        asyncio.run(evaluate_mode())