"""
train_ids_model.py
-------------------
Reproducible training pipeline for SecureLend's hybrid IDS ML layer.

This regenerates the synthetic training data, trains both models used in
production (a supervised RandomForestClassifier for attack-type
classification, and an unsupervised IsolationForest for catching anything
outside the classifier's training distribution), evaluates them properly,
and writes out everything ids_inference.py expects to find in this folder.

WHY SYNTHETIC DATA, NOT A PUBLIC BENCHMARK (e.g. NSL-KDD/CICIDS2017):
Those datasets describe raw network packet/flow features (packet counts,
byte counts, TCP flags, protocol types) captured at the network layer.
This IDS operates at the *application* layer instead -- it reasons about
HTTP request semantics (payload content, endpoint sensitivity, auth role,
request rate per identity) that only exist once a request has already
been parsed by a web framework. There's no direct feature mapping between
the two layers, so synthetic generation aligned to this system's actual
feature schema is the correct choice here, not a compromise -- but this
is exactly the kind of design decision to state explicitly and defend in
a report, rather than leave implicit.

Run this from backend/ml/ with your venv active:
    python train_ids_model.py

Outputs (all written to this folder):
    attack_classifier.pkl     -- RandomForestClassifier
    anomaly_detector.pkl      -- IsolationForest (trained on 'normal' class only)
    feature_scaler.pkl        -- StandardScaler fit on training features
    label_encoder.pkl         -- LabelEncoder for the 8 class names
    model_card.json           -- summary stats (matches existing schema)
    evaluation_report.txt     -- full classification report + confusion matrix
    confusion_matrix.png      -- visual confusion matrix for your report
"""
import json
import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, confusion_matrix, precision_recall_fscore_support,
    roc_auc_score,
)

RANDOM_SEED = 42
rng = np.random.default_rng(RANDOM_SEED)

FEATURES = [
    "requests_per_minute", "failed_logins_5min", "contains_sql_keywords",
    "contains_script_tag", "endpoint_sensitivity", "role_mismatch",
    "file_ext_risk", "payload_size_kb", "unique_endpoints_1min", "hour_of_day",
]
CLASSES = [
    "anomalous_traffic", "bot_flood", "brute_force_login", "malicious_upload",
    "normal", "sql_injection", "unauthorized_admin", "xss_attempt",
]
SAMPLES_PER_CLASS = 3937  # -> ~31500 total (25200 train / 6300 test @ 80/20)


def _clip(x, lo, hi):
    return np.clip(x, lo, hi)


def generate_class_samples(label: str, n: int) -> pd.DataFrame:
    """Each class has a distinct-but-overlapping feature distribution --
    deliberately noisy/overlapping rather than perfectly separable, since
    real traffic isn't perfectly separable either and a model trained on
    trivially-separable synthetic data would report unrealistically high
    accuracy that wouldn't hold up under scrutiny."""

    if label == "normal":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(8, 4, n), 0, 40),
            "failed_logins_5min": rng.choice([0, 0, 0, 0, 1], n),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": rng.choice([0, 0, 1, 1, 1, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "file_ext_risk": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "payload_size_kb": _clip(rng.exponential(3, n), 0.1, 50),
            "unique_endpoints_1min": _clip(rng.poisson(2, n), 1, 15),
            "hour_of_day": rng.integers(0, 24, n),
        })
    elif label == "sql_injection":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(15, 8, n), 1, 60),
            "failed_logins_5min": rng.choice([0, 0, 0, 1, 2], n),
            "contains_sql_keywords": rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 0], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": rng.choice([0, 1, 1, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 1], n),
            "file_ext_risk": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "payload_size_kb": _clip(rng.exponential(4, n), 0.2, 60),
            "unique_endpoints_1min": _clip(rng.poisson(3, n), 1, 20),
            "hour_of_day": rng.integers(0, 24, n),
        })
    elif label == "xss_attempt":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(12, 7, n), 1, 55),
            "failed_logins_5min": rng.choice([0, 0, 0, 1], n),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 0], n),
            "endpoint_sensitivity": rng.choice([0, 1, 1, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 1], n),
            "file_ext_risk": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "payload_size_kb": _clip(rng.exponential(3.5, n), 0.2, 55),
            "unique_endpoints_1min": _clip(rng.poisson(3, n), 1, 20),
            "hour_of_day": rng.integers(0, 24, n),
        })
    elif label == "brute_force_login":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(35, 15, n), 5, 120),
            "failed_logins_5min": _clip(rng.poisson(12, n), 3, 40),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": rng.choice([1, 1, 1, 1, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 1], n),
            "file_ext_risk": np.zeros(n, dtype=int),
            "payload_size_kb": _clip(rng.exponential(1, n), 0.1, 10),
            "unique_endpoints_1min": _clip(rng.poisson(1, n), 1, 5),
            "hour_of_day": rng.integers(0, 24, n),
        })
    elif label == "bot_flood":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(150, 60, n), 60, 500),
            "failed_logins_5min": rng.choice([0, 0, 0, 1, 2], n),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": rng.choice([0, 0, 1, 1, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 1], n),
            "file_ext_risk": np.zeros(n, dtype=int),
            "payload_size_kb": _clip(rng.exponential(1.5, n), 0.1, 15),
            "unique_endpoints_1min": _clip(rng.poisson(8, n), 1, 30),
            "hour_of_day": rng.integers(0, 24, n),
        })
    elif label == "malicious_upload":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(10, 6, n), 1, 45),
            "failed_logins_5min": rng.choice([0, 0, 0, 0, 1], n),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": rng.choice([1, 1, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 1], n),
            "file_ext_risk": rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 0], n),
            "payload_size_kb": _clip(rng.exponential(200, n), 5, 5000),
            "unique_endpoints_1min": _clip(rng.poisson(2, n), 1, 10),
            "hour_of_day": rng.integers(0, 24, n),
        })
    elif label == "unauthorized_admin":
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(10, 6, n), 1, 45),
            "failed_logins_5min": rng.choice([0, 0, 0, 0, 1], n),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": np.full(n, 2),
            "role_mismatch": rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 0], n),
            "file_ext_risk": rng.choice([0, 0, 0, 0, 0, 0, 0, 0, 1], n),
            "payload_size_kb": _clip(rng.exponential(2, n), 0.1, 20),
            "unique_endpoints_1min": _clip(rng.poisson(3, n), 1, 15),
            "hour_of_day": rng.integers(0, 24, n),
        })
    else:  # anomalous_traffic -- deliberately diffuse/mixed, no single dominant signal
        df = pd.DataFrame({
            "requests_per_minute": _clip(rng.normal(45, 25, n), 5, 200),
            "failed_logins_5min": _clip(rng.poisson(3, n), 0, 15),
            "contains_sql_keywords": rng.choice([0, 0, 0, 0, 0, 0, 0, 1], n),
            "contains_script_tag": rng.choice([0, 0, 0, 0, 0, 0, 0, 1], n),
            "endpoint_sensitivity": rng.choice([0, 1, 1, 2, 2], n),
            "role_mismatch": rng.choice([0, 0, 0, 0, 1], n),
            "file_ext_risk": rng.choice([0, 0, 0, 0, 0, 0, 0, 1], n),
            "payload_size_kb": _clip(rng.exponential(20, n), 0.5, 300),
            "unique_endpoints_1min": _clip(rng.poisson(6, n), 1, 25),
            "hour_of_day": rng.integers(0, 24, n),
        })

    df["label"] = label
    return df


def main():
    print(f"Generating {SAMPLES_PER_CLASS} samples per class x {len(CLASSES)} classes...")
    frames = [generate_class_samples(c, SAMPLES_PER_CLASS) for c in CLASSES]
    data = pd.concat(frames, ignore_index=True).sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
    print(f"Total samples: {len(data)}")

    X = data[FEATURES].values
    y_raw = data["label"].values

    le = LabelEncoder()
    le.fit(CLASSES)  # fixed order, matches classes_in_order in model_card.json
    y = le.transform(y_raw)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )
    print(f"Train: {len(X_train)}  Test: {len(X_test)}")

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # --- Supervised classifier ---
    print("\nTraining RandomForestClassifier...")
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=12, min_samples_leaf=5,
        random_state=RANDOM_SEED, class_weight="balanced", n_jobs=-1,
    )
    clf.fit(X_train_s, y_train)

    y_pred = clf.predict(X_test_s)
    report = classification_report(y_test, y_pred, target_names=le.classes_, digits=4)
    print(report)

    cm = confusion_matrix(y_test, y_pred)
    precisions, recalls, f1s, supports = precision_recall_fscore_support(y_test, y_pred, zero_division=0)

    # Attack-only recall (excludes 'normal' class) -- the headline metric
    # that matters most for an IDS: of all real attacks, how many did we catch?
    normal_idx = list(le.classes_).index("normal")
    attack_mask_true = y_test != normal_idx
    attack_recall = (y_pred[attack_mask_true] != normal_idx).mean()

    # False positive rate: of all genuinely normal traffic, how much did we
    # wrongly flag as an attack?
    normal_mask_true = y_test == normal_idx
    false_positive_rate = (y_pred[normal_mask_true] != normal_idx).mean()

    # Feature importance -- worth including in your report as it directly
    # explains *why* the model flags what it flags, consistent with this
    # project's explainable-AI theme elsewhere (loan scoring).
    importances = sorted(zip(FEATURES, clf.feature_importances_), key=lambda x: -x[1])

    # --- Unsupervised anomaly detector, trained on 'normal' traffic only ---
    print("\nTraining IsolationForest on normal-traffic baseline...")
    normal_train_mask = y_train == normal_idx
    iso = IsolationForest(
        n_estimators=200, contamination=0.1, random_state=RANDOM_SEED, n_jobs=-1
    )
    iso.fit(X_train_s[normal_train_mask])

    # Threshold = 90th percentile of anomaly scores on held-out *normal*
    # test traffic -- i.e. tuned so ~10% of genuinely normal traffic sits
    # above threshold (matching the classifier's false_positive_rate ballpark),
    # not tuned by peeking at attack traffic.
    normal_test_mask = y_test == normal_idx
    normal_scores = -iso.decision_function(X_test_s[normal_test_mask])
    anomaly_threshold = float(np.percentile(normal_scores, 90))

    # --- Save all artifacts ---
    joblib.dump(clf, "attack_classifier.pkl")
    joblib.dump(iso, "anomaly_detector.pkl")
    joblib.dump(scaler, "feature_scaler.pkl")
    joblib.dump(le, "label_encoder.pkl")

    model_card = {
        "features_in_order": FEATURES,
        "classes_in_order": list(le.classes_),
        "anomaly_threshold": anomaly_threshold,
        "training_rows": len(X_train),
        "test_rows": len(X_test),
        "attack_recall_at_threshold": float(attack_recall),
        "false_positive_rate_at_threshold": float(false_positive_rate),
        "random_seed": RANDOM_SEED,
        "model_type": "RandomForestClassifier (supervised) + IsolationForest (unsupervised)",
        "per_class_precision": {c: round(float(p), 4) for c, p in zip(le.classes_, precisions)},
        "per_class_recall": {c: round(float(r), 4) for c, r in zip(le.classes_, recalls)},
        "per_class_f1": {c: round(float(f), 4) for c, f in zip(le.classes_, f1s)},
        "feature_importances": {f: round(float(v), 4) for f, v in importances},
    }
    with open("model_card.json", "w") as f:
        json.dump(model_card, f, indent=2)

    with open("evaluation_report.txt", "w") as f:
        f.write("SecureLend IDS -- Model Evaluation Report\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Random seed: {RANDOM_SEED}\n")
        f.write(f"Total samples: {len(data)}  (Train: {len(X_train)} / Test: {len(X_test)})\n\n")
        f.write("Classification Report:\n")
        f.write(report)
        f.write("\n\nConfusion Matrix (rows=true, cols=predicted):\n")
        f.write(f"Classes: {list(le.classes_)}\n")
        f.write(np.array2string(cm))
        f.write(f"\n\nAttack recall (headline metric): {attack_recall:.4f}\n")
        f.write(f"False positive rate on normal traffic: {false_positive_rate:.4f}\n")
        f.write(f"IsolationForest anomaly threshold: {anomaly_threshold:.4f}\n\n")
        f.write("Feature importances (RandomForest, sorted):\n")
        for feat, imp in importances:
            f.write(f"  {feat}: {imp:.4f}\n")

    # Confusion matrix plot
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(le.classes_)))
    ax.set_yticks(range(len(le.classes_)))
    ax.set_xticklabels(le.classes_, rotation=45, ha="right")
    ax.set_yticklabels(le.classes_)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("SecureLend IDS -- Confusion Matrix")
    for i in range(len(le.classes_)):
        for j in range(len(le.classes_)):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=8)
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig("confusion_matrix.png", dpi=150)

    print("\nDone. Wrote: attack_classifier.pkl, anomaly_detector.pkl, feature_scaler.pkl,")
    print("label_encoder.pkl, model_card.json, evaluation_report.txt, confusion_matrix.png")
    print(f"\nAttack recall: {attack_recall:.4f}  |  False positive rate: {false_positive_rate:.4f}")


if __name__ == "__main__":
    main()