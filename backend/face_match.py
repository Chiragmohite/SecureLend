"""
face_match.py
-------------
Duplicate-face detection for registration, using geometric face-landmark
embeddings computed client-side (see frontend/src/lib/faceEmbedding.js).

This is NOT a deep-learning face-recognition system (FaceNet/ArcFace/etc.).
It compares small vectors (16 floats) of normalized inter-landmark
distances, computed in the browser from MediaPipe's face-mesh detector.
This is a classical, explainable geometric approach: good enough to catch
someone registering multiple accounts with visibly the same face in a
demo/academic setting.

Explicitly NOT claimed here: production-grade biometric security. There's
no liveness/spoof detection (a captured frame is trusted as-is), and the
descriptor is sensitive to pose, lighting, and facial expression. A real
deployment would use a trained face-recognition embedding model evaluated
server-side on the actual image, plus liveness checks -- state this
limitation in any report/write-up.
"""
import math
from typing import List, Optional, Sequence, Tuple

# Expected embedding length -- must match faceEmbedding.js's PAIRS array.
EMBEDDING_LENGTH = 16

# Euclidean distance between two normalized embeddings below which we
# treat two captures as "the same face". Tuned empirically against the
# normalization scheme in faceEmbedding.js (interocular-distance-scaled
# landmark distances) -- lower = stricter (fewer false positives, more
# false negatives), higher = looser.
#
# NOTE ON CALIBRATION: this geometric approach is inherently noisier across
# separate capture sessions than a trained deep-learning embedding would
# be -- pose, lighting, and expression shift the individual distances
# noticeably even for the same real face. 0.25 proved too strict in
# practice (two registrations with the same face weren't being caught).
# Raised to 0.55 as a looser default. See closest_face_distance() below --
# server.py logs the actual distance on every registration attempt, so
# real numbers from your own testing can be used to tune this further
# rather than guessing blind.
DUPLICATE_FACE_THRESHOLD = 0.55


def closest_face_distance(
    new_embedding: Sequence[float],
    existing: List[Tuple[str, List[float]]],
) -> Optional[Tuple[str, float]]:
    """Returns (closest_user_id, distance) for logging/calibration purposes,
    or None if there's nothing to compare against. Distinct from
    find_duplicate_face() so callers can log the real number regardless of
    whether it crosses the threshold."""
    if not new_embedding or not existing:
        return None
    best_id, best_dist = None, float("inf")
    for user_id, emb in existing:
        d = embedding_distance(new_embedding, emb)
        if d < best_dist:
            best_id, best_dist = user_id, d
    return (best_id, best_dist) if best_id is not None else None


def is_valid_embedding(embedding) -> bool:
    return (
        isinstance(embedding, (list, tuple))
        and len(embedding) == EMBEDDING_LENGTH
        and all(isinstance(v, (int, float)) for v in embedding)
    )


def embedding_distance(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def find_duplicate_face(
    new_embedding: Sequence[float],
    existing: List[Tuple[str, List[float]]],
) -> Optional[str]:
    """existing: list of (user_id, embedding) for other registered users
    who have a stored face embedding. Returns the matching user_id if a
    duplicate face is found, else None."""
    if not new_embedding:
        return None
    best_id, best_dist = None, float("inf")
    for user_id, emb in existing:
        d = embedding_distance(new_embedding, emb)
        if d < best_dist:
            best_id, best_dist = user_id, d
    if best_dist < DUPLICATE_FACE_THRESHOLD:
        return best_id
    return None