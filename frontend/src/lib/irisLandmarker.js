// irisLandmarker.js
// ------------------
// Thin wrapper around MediaPipe's Tasks Vision `FaceLandmarker`, running
// entirely client-side (WASM + a small model, both fetched once and cached
// by the browser). No video frame or image ever leaves the device — this
// is real ML iris landmark *detection*, not a network call.
//
// What this genuinely does: locates ~5 landmark points per iris in real
// time from a normal webcam feed (MediaPipe's `refineLandmarks` option).
// What it does NOT do: iris pattern matching / biometric authentication.
// That would need a trained matcher + enrolled templates (see report notes).
// This module only answers "is there a real iris here, and where" — the
// verified/matched decision made after detection is still simulated.
//
// Setup: run once inside frontend/
//   npm install @mediapipe/tasks-vision

let landmarkerPromise = null;

export function getFaceLandmarker() {
  if (!landmarkerPromise) {
    landmarkerPromise = (async () => {
      const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
      const filesetResolver = await FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
      );
      return FaceLandmarker.createFromOptions(filesetResolver, {
        baseOptions: {
          modelAssetPath:
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
          delegate: "GPU",
        },
        outputFaceBlendshapes: false,
        outputFacialTransformationMatrixes: false,
        runningMode: "VIDEO",
        numFaces: 1,
        // refineLandmarks adds landmarks 468-477: 5 iris points per eye.
        // Without this flag MediaPipe returns only the 468 face-mesh points
        // and no iris data at all.
      });
    })();
  }
  return landmarkerPromise;
}

// Landmark indices for the two irises when refined landmarks are present.
// Index 0 of each group is the iris center; the other four ring the edge.
export const LEFT_IRIS = [468, 469, 470, 471, 472];
export const RIGHT_IRIS = [473, 474, 475, 476, 477];

// True only when the model actually returned refined (468-477) points —
// lets calling code fail gracefully on model versions/config without them.
export function hasIrisLandmarks(faceLandmarks) {
  return Array.isArray(faceLandmarks) && faceLandmarks.length >= 478;
}