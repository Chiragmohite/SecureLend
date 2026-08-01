// faceEmbedding.js
// ------------------
// Computes a lightweight geometric face descriptor from MediaPipe's
// FaceLandmarker output (the same on-device model already used for the
// iris scan -- see irisLandmarker.js).
//
// What this genuinely is: a vector of normalized distances between fixed
// anchor points on the face (eye corners, nose, mouth, jaw, brows), scaled
// by inter-ocular distance so it's roughly invariant to how close the
// person is to the camera. This is a classical geometric face-descriptor
// approach (pre-dating deep-learning face recognition), not a trained
// embedding model like FaceNet/ArcFace.
//
// What it's good enough for: telling two clearly different faces apart,
// or flagging that the *same* face is being used to register a second
// account, for a demo/academic project.
// What it is NOT: production-grade biometric security. It has no liveness
// or spoof detection, and is sensitive to pose, lighting, and expression.
// A real deployment would use a trained face-recognition embedding model
// (server-side, on the actual image) plus liveness checks, not this.
//
// Nothing here ever leaves the browser except the final small numeric
// vector (16 floats) -- never the image/video itself.

// Canonical MediaPipe Face Mesh landmark indices used as anchor points.
const L_EYE_OUTER = 33, L_EYE_INNER = 133;
const R_EYE_OUTER = 263, R_EYE_INNER = 362;
const NOSE_TIP = 1, NOSE_BRIDGE = 6;
const MOUTH_LEFT = 61, MOUTH_RIGHT = 291;
const MOUTH_TOP = 13, MOUTH_BOTTOM = 14;
const CHIN = 152, FOREHEAD = 10;
const L_CHEEK = 234, R_CHEEK = 454;
const L_BROW = 105, R_BROW = 334;

// Highest landmark index referenced above -- used to sanity-check that a
// full face-mesh result (478 points w/ iris) came back before we index in.
const MAX_INDEX_USED = R_CHEEK;

function dist3(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y, (a.z || 0) - (b.z || 0));
}

// Landmark index pairs whose normalized distance forms the embedding.
// Chosen to span the whole face (eyes, nose, mouth, jaw, brows) so the
// vector captures overall face geometry, not just one region.
const PAIRS = [
  [L_EYE_OUTER, L_EYE_INNER], [R_EYE_OUTER, R_EYE_INNER],
  [L_EYE_INNER, R_EYE_INNER], [NOSE_TIP, CHIN], [NOSE_TIP, FOREHEAD],
  [NOSE_BRIDGE, NOSE_TIP], [MOUTH_LEFT, MOUTH_RIGHT], [MOUTH_TOP, MOUTH_BOTTOM],
  [L_CHEEK, R_CHEEK], [CHIN, FOREHEAD], [L_EYE_OUTER, MOUTH_LEFT],
  [R_EYE_OUTER, MOUTH_RIGHT], [L_BROW, L_EYE_OUTER], [R_BROW, R_EYE_OUTER],
  [L_EYE_OUTER, NOSE_TIP], [R_EYE_OUTER, NOSE_TIP],
];

/**
 * @param {Array<{x:number,y:number,z?:number}>} landmarks - a single face's
 *   landmark array from FaceLandmarker's `faceLandmarks[0]`.
 * @returns {number[]|null} a 16-dim normalized distance vector, or null if
 *   the landmarks look incomplete/unusable.
 */
export function computeFaceEmbedding(landmarks) {
  if (!Array.isArray(landmarks) || landmarks.length <= MAX_INDEX_USED) return null;

  const interocular = dist3(landmarks[L_EYE_OUTER], landmarks[R_EYE_OUTER]);
  if (!interocular || interocular < 1e-6) return null;

  return PAIRS.map(([i, j]) => dist3(landmarks[i], landmarks[j]) / interocular);
}