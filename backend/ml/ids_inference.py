"""
ids_inference.py
-----------------
Drop this file (+ the 4 .pkl artifacts in this folder) into your FastAPI
backend, e.g. under app/ml/. It exposes one function, score_request(),
that your IDS middleware calls on every incoming API request.

Usage in FastAPI middleware:

    from app.ml.ids_inference import score_request

    @app.middleware("http")
    async def ids_middleware(request, call_next):
        features = extract_features(request)   # you compute these per-request
        result = score_request(features)
        if result["action"] == "block":
            return JSONResponse(status_code=403, content={"detail": "Blocked by IDS", **result})
        response = await call_next(request)
        return response

`extract_features` is on you to wire up (it just needs to read/derive the
10 fields below from request metadata + a short rolling window per IP,
which you likely already track for rate limiting).
"""

import os
import joblib
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))

_clf = joblib.load(os.path.join(_DIR, "attack_classifier.pkl"))
_iso = joblib.load(os.path.join(_DIR, "anomaly_detector.pkl"))
_scaler = joblib.load(os.path.join(_DIR, "feature_scaler.pkl"))
_le = joblib.load(os.path.join(_DIR, "label_encoder.pkl"))

FEATURES = [
    "requests_per_minute",
    "failed_logins_5min",
    "contains_sql_keywords",
    "contains_script_tag",
    "endpoint_sensitivity",
    "role_mismatch",
    "file_ext_risk",
    "payload_size_kb",
    "unique_endpoints_1min",
    "hour_of_day",
]

# Load the anomaly threshold saved during training (90th percentile of normal traffic scores)
import json
with open(os.path.join(_DIR, "model_card.json")) as f:
    _ANOMALY_THRESHOLD = json.load(f)["anomaly_threshold"]


def score_request(feature_dict: dict) -> dict:
    """
    feature_dict must contain all keys in FEATURES (see docstring above).
    Returns a dict describing the classifier's verdict, the anomaly score,
    and a recommended action for your middleware to enforce.
    """
    x = np.array([[feature_dict[k] for k in FEATURES]])
    x_s = _scaler.transform(x)

    # 1. Signature-style classification (what kind of attack, if any)
    pred_idx = _clf.predict(x_s)[0]
    pred_label = _le.inverse_transform([pred_idx])[0]
    pred_proba = float(_clf.predict_proba(x_s)[0][pred_idx])

    # 2. Unsupervised anomaly score (catches things the classifier wasn't trained on)
    anomaly_score = float(-_iso.decision_function(x_s)[0])
    is_anomalous = anomaly_score > _ANOMALY_THRESHOLD

    is_known_attack = pred_label != "normal"

    if is_known_attack and pred_proba > 0.8:
        action = "block"
        severity = "high"
    elif is_known_attack or is_anomalous:
        action = "flag"
        severity = "medium"
    else:
        action = "allow"
        severity = "low"

    return {
        "predicted_type": pred_label,
        "confidence": round(pred_proba, 4),
        "anomaly_score": round(anomaly_score, 4),
        "anomaly_threshold": round(_ANOMALY_THRESHOLD, 4),
        "is_anomalous": bool(is_anomalous),
        "action": action,       # "block" | "flag" | "allow"
        "severity": severity,   # "high" | "medium" | "low"
    }


if __name__ == "__main__":
    # quick smoke test
    normal_example = {
        "requests_per_minute": 5, "failed_logins_5min": 0, "contains_sql_keywords": 0,
        "contains_script_tag": 0, "endpoint_sensitivity": 1, "role_mismatch": 0,
        "file_ext_risk": 0, "payload_size_kb": 2.1, "unique_endpoints_1min": 2, "hour_of_day": 14,
    }
    sqli_example = {**normal_example, "contains_sql_keywords": 1, "requests_per_minute": 12}
    brute_force_example = {**normal_example, "requests_per_minute": 40, "failed_logins_5min": 18, "endpoint_sensitivity": 1}

    for name, ex in [("normal", normal_example), ("sqli", sqli_example), ("brute_force", brute_force_example)]:
        print(name, "->", score_request(ex))
