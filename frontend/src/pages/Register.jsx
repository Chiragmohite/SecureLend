import { useState, useRef, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, ArrowRight, CheckCircle2, KeyRound, IdCard, User, ScanFace } from "lucide-react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { getFaceLandmarker, LEFT_IRIS, hasIrisLandmarks } from "@/lib/irisLandmarker";
import { computeFaceEmbedding } from "@/lib/faceEmbedding";
import { scorePasswordStrength } from "@/lib/passwordStrength";

// Consecutive detection frames required before we call the scan "locked on"
// (~1.5s at a typical 30fps webcam) -- long enough to rule out a stray
// single-frame false positive, short enough to still feel responsive.
const IRIS_LOCK_FRAMES = 45;
const IRIS_CANVAS_SIZE = 220;

const STEPS = [
  { key: "phone", label: "Mobile", icon: KeyRound },
  { key: "pan",   label: "PAN",    icon: IdCard },
  { key: "info",  label: "Profile", icon: User },
  { key: "face",  label: "Face",    icon: ScanFace },
];

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);

  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [demoOtp, setDemoOtp] = useState("");
  const [phoneVerified, setPhoneVerified] = useState(false);

  const [pan, setPan] = useState("");
  const [panVerified, setPanVerified] = useState(false);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [dob, setDob] = useState("");
  const [password, setPassword] = useState("");
  const pwStrength = scorePasswordStrength(password);

  // --- Face verification state ---
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [cameraError, setCameraError] = useState("");
  const [faceStatus, setFaceStatus] = useState("idle"); // idle | streaming | capturing | verified
  const [capturedFrame, setCapturedFrame] = useState(null);
  const [faceEmbedding, setFaceEmbedding] = useState(null);

  useEffect(() => {
    if (step === 3) startCamera();
    return () => stopCamera();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const startCamera = async () => {
    setCameraError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setFaceStatus("streaming");
    } catch (err) {
      setCameraError("Camera access denied or unavailable. You can skip this step for now.");
      setFaceStatus("idle");
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  };

  const captureAndVerify = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    setFaceStatus("capturing");

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 480;
    canvas.height = video.videoHeight || 360;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    setCapturedFrame(canvas.toDataURL("image/jpeg", 0.7));

    // Real part: run MediaPipe's FaceLandmarker (same on-device model as
    // the iris scan) on the captured frame and compute a geometric
    // embedding from the 468 face-mesh points (see faceEmbedding.js).
    // That embedding -- a 16-number vector, never the image itself -- is
    // what gets sent to the backend at account creation, so it can check
    // whether this face is already tied to another registered account.
    // Simulated part: there's still no liveness/anti-spoof check (e.g.
    // distinguishing a live person from a photo held up to the camera) --
    // a real deployment would add that server-side too.
    try {
      const landmarker = await getFaceLandmarker();
      const results = landmarker.detectForVideo(canvas, performance.now());
      const face = results.faceLandmarks && results.faceLandmarks[0];
      const embedding = face ? computeFaceEmbedding(face) : null;

      if (!embedding) {
        setFaceStatus("streaming");
        toast.error("No face detected clearly -- center your face in frame with good lighting and try again.");
        return;
      }

      setFaceEmbedding(embedding);
      stopCamera();
      setFaceStatus("verified");
      toast.success("Face captured");
    } catch (err) {
      setFaceStatus("streaming");
      toast.error("Couldn't process the face scan. Check camera permissions and try again.");
    }
  };

  // --- Iris scan state ---
  // Real part: MediaPipe's FaceLandmarker actually locates the iris live,
  // client-side, from the webcam feed below (no image ever leaves the
  // browser). Simulated part: once it's tracked the iris steadily for
  // IRIS_LOCK_FRAMES frames, we treat that as a "match" -- there's no
  // enrolled template or real biometric comparison happening.
  const [showIris, setShowIris] = useState(false);
  const [irisStatus, setIrisStatus] = useState("idle"); // idle | loading | scanning | verified | error
  const [irisHint, setIrisHint] = useState("");
  const irisVideoRef = useRef(null);
  const irisCanvasRef = useRef(null);
  const irisStreamRef = useRef(null);
  const irisRafRef = useRef(null);
  const irisLockFramesRef = useRef(0);

  useEffect(() => {
    return () => stopIrisScan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopIrisScan = () => {
    if (irisRafRef.current) cancelAnimationFrame(irisRafRef.current);
    irisRafRef.current = null;
    if (irisStreamRef.current) {
      irisStreamRef.current.getTracks().forEach((t) => t.stop());
      irisStreamRef.current = null;
    }
  };

  const runIrisScan = async () => {
    setIrisStatus("loading");
    irisLockFramesRef.current = 0;
    try {
      const [landmarker, stream] = await Promise.all([
        getFaceLandmarker(),
        navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false }),
      ]);
      irisStreamRef.current = stream;
      if (irisVideoRef.current) {
        irisVideoRef.current.srcObject = stream;
        await irisVideoRef.current.play();
      }
      setIrisStatus("scanning");
      irisRafRef.current = requestAnimationFrame(() => irisDetectLoop(landmarker));
    } catch (err) {
      setIrisStatus("error");
      setIrisHint("Couldn't start the camera or load the iris model. Check camera permission and your connection.");
    }
  };

  const irisDetectLoop = (landmarker) => {
    const video = irisVideoRef.current;
    const canvas = irisCanvasRef.current;
    if (!video || !canvas || video.readyState < 2) {
      irisRafRef.current = requestAnimationFrame(() => irisDetectLoop(landmarker));
      return;
    }

    if (canvas.width !== IRIS_CANVAS_SIZE) {
      canvas.width = IRIS_CANVAS_SIZE;
      canvas.height = IRIS_CANVAS_SIZE;
    }
    const ctx = canvas.getContext("2d");
    const vw = video.videoWidth, vh = video.videoHeight;
    const results = landmarker.detectForVideo(video, performance.now());
    const face = results.faceLandmarks && results.faceLandmarks[0];

    if (face && hasIrisLandmarks(face)) {
      const center = face[LEFT_IRIS[0]];
      const edge = face[LEFT_IRIS[1]];
      const cx = center.x * vw, cy = center.y * vh;
      const ex = edge.x * vw, ey = edge.y * vh;
      const irisRadiusPx = Math.max(Math.hypot(ex - cx, ey - cy), 4);
      const half = irisRadiusPx * 7; // zoom padding around the iris

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(video, cx - half, cy - half, half * 2, half * 2, 0, 0, IRIS_CANVAS_SIZE, IRIS_CANVAS_SIZE);

      // Detection ring, confirming a real landmark lock (not decorative-only)
      ctx.strokeStyle = "rgba(46,125,70,0.75)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(IRIS_CANVAS_SIZE / 2, IRIS_CANVAS_SIZE / 2, IRIS_CANVAS_SIZE * 0.32, 0, Math.PI * 2);
      ctx.stroke();

      // Sweeping scan line
      const t = (performance.now() % 1400) / 1400;
      ctx.strokeStyle = "rgba(46,125,70,0.9)";
      ctx.beginPath();
      ctx.moveTo(0, t * IRIS_CANVAS_SIZE);
      ctx.lineTo(IRIS_CANVAS_SIZE, t * IRIS_CANVAS_SIZE);
      ctx.stroke();

      irisLockFramesRef.current += 1;
      setIrisHint("");
    } else {
      irisLockFramesRef.current = 0;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      setIrisHint("Center one eye in frame and hold still.");
    }

    if (irisLockFramesRef.current >= IRIS_LOCK_FRAMES) {
      stopIrisScan();
      setIrisStatus("verified");
      toast.success("Iris detected and matched (simulated match decision)");
      return;
    }
    irisRafRef.current = requestAnimationFrame(() => irisDetectLoop(landmarker));
  };

  const skipFace = () => {
    stopCamera();
    setFaceStatus("verified");
  };

  const [realSms, setRealSms] = useState(false);

  const sendOtp = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/otp/send", { phone });
      setOtpSent(true);
      setDemoOtp(data.demo_otp || "");
      setRealSms(!!data.real_sms);
      toast.success(data.real_sms ? "OTP sent via SMS" : "OTP sent (demo shown below)");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const verifyOtp = async () => {
    setBusy(true);
    try {
      await api.post("/otp/verify", { phone, otp });
      setPhoneVerified(true);
      toast.success("Mobile verified");
      setStep(1);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const checkPan = async () => {
    setBusy(true);
    try {
      await api.post("/kyc/pan-check", { pan: pan.toUpperCase() });
      setPanVerified(true);
      toast.success("PAN verified");
      setStep(2);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const goToFaceStep = (e) => {
    e.preventDefault();
    if (pwStrength.score === 0) {
      toast.error(pwStrength.feedback[0] || "Choose a stronger password before continuing.");
      return;
    }
    setStep(3);
  };

  const submit = async () => {
    setBusy(true);
    try {
      await register({ full_name: fullName, email, password, dob, phone, pan: pan.toUpperCase(), face_embedding: faceEmbedding });
      toast.success("Welcome to SecureLend!");
      nav("/app", { replace: true });
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="user-portal min-h-screen">
      <header className="max-w-5xl mx-auto flex items-center justify-between px-6 py-5">
        <Link to="/" className="flex items-center gap-2" data-testid="reg-brand">
          <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
            <ShieldCheck className="text-white" size={18} />
          </div>
          <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
        </Link>
        <Link to="/login" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }} data-testid="link-login">Already registered? Sign in</Link>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10">
        <h1 className="font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>Create your account</h1>
        <p className="mt-2" style={{ color: "var(--sl-muted)" }}>Four quick steps. All fields are sanitised at the IDS layer before they reach the DB.</p>

        {/* Stepper */}
        <div className="mt-8 flex items-center gap-3 flex-wrap">
          {STEPS.map((s, i) => {
            const done = i < step;
            const active = i === step;
            const Icon = s.icon;
            return (
              <div key={s.key} className="flex items-center gap-3">
                <div className="step-dot" style={{
                  background: done ? "var(--sl-primary)" : (active ? "var(--sl-accent)" : "#E5E7DF"),
                  color: (done || active) ? "#FFF" : "var(--sl-muted)"
                }}>
                  {done ? <CheckCircle2 size={16}/> : <Icon size={14}/>}
                </div>
                <span className={`text-sm ${active ? "font-semibold" : ""}`} style={{ color: active ? "var(--sl-primary)" : "var(--sl-muted)" }}>{s.label}</span>
                {i < STEPS.length - 1 && <span className="w-8 h-px" style={{ background: "var(--sl-border)" }} />}
              </div>
            );
          })}
        </div>

        {/* Step 0: phone */}
        {step === 0 && (
          <div className="u-card p-8 mt-8" data-testid="reg-step-phone">
            <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Mobile number (India)</label>
            <div className="flex gap-3 mt-2">
              <div className="px-4 py-3 rounded-lg font-mono text-sm" style={{ background: "#EFF1E9", color: "var(--sl-primary)" }}>+91</div>
              <input data-testid="reg-phone" value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
                     className="flex-1 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} placeholder="10-digit mobile" />
            </div>

            {!otpSent && (
              <button data-testid="reg-send-otp" disabled={phone.length !== 10 || busy} onClick={sendOtp} className="btn-primary mt-6">{busy ? "Sending…" : "Send OTP"}</button>
            )}
            {otpSent && (
              <>
                {realSms ? (
                  <div className="mt-4 text-xs" style={{ color: "var(--sl-accent)" }} data-testid="reg-real-sms-note">
                    A text message with your code was sent to +91-{phone}.
                  </div>
                ) : (
                  <div className="mt-4 text-xs" style={{ color: "var(--sl-accent)" }} data-testid="reg-demo-otp">Demo OTP: <span className="font-mono">{demoOtp}</span></div>
                )}
                <label className="block mt-5 text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Enter OTP</label>
                <input data-testid="reg-otp" value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                       className="w-full mt-2 px-4 py-3 rounded-lg border font-mono tracking-widest text-lg outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} placeholder="6-digit code"/>
                <button data-testid="reg-verify-otp" disabled={otp.length !== 6 || busy} onClick={verifyOtp} className="btn-primary mt-6">Verify & continue</button>
              </>
            )}
          </div>
        )}

        {/* Step 1: PAN */}
        {step === 1 && (
          <div className="u-card p-8 mt-8" data-testid="reg-step-pan">
            <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>PAN number</label>
            <input data-testid="reg-pan" value={pan} onChange={(e) => setPan(e.target.value.toUpperCase().slice(0, 10))}
                   className="w-full mt-2 px-4 py-3 rounded-lg border font-mono tracking-widest outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} placeholder="ABCDE1234F"/>
            <div className="mt-2 text-xs" style={{ color: "var(--sl-muted)" }}>Format: 5 letters, 4 digits, 1 letter.</div>
            <button data-testid="reg-verify-pan" disabled={pan.length !== 10 || busy} onClick={checkPan} className="btn-primary mt-6">Verify PAN</button>
          </div>
        )}

        {/* Step 2: profile */}
        {step === 2 && (
          <form onSubmit={goToFaceStep} className="u-card p-8 mt-8" data-testid="reg-step-info">
            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Full name</label>
                <input required data-testid="reg-name" value={fullName} onChange={(e)=>setFullName(e.target.value)}
                       className="w-full mt-2 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Date of birth</label>
                <input required data-testid="reg-dob" type="date" value={dob} onChange={(e)=>setDob(e.target.value)}
                       className="w-full mt-2 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Email</label>
                <input required data-testid="reg-email" type="email" value={email} onChange={(e)=>setEmail(e.target.value)}
                       className="w-full mt-2 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Password</label>
                <input required data-testid="reg-password" type="password" minLength={6} value={password} onChange={(e)=>setPassword(e.target.value)}
                       className="w-full mt-2 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} placeholder="At least 6 characters"/>
                {password && (
                  <div className="mt-2" data-testid="reg-password-strength">
                    <div className="flex gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <div key={i} className="h-1.5 flex-1 rounded-full" style={{
                          background: i <= pwStrength.score
                            ? ["#8A2A17", "#B47A1B", "#4C7A3D", "#1A3626"][pwStrength.score]
                            : "#E5E7DF"
                        }} />
                      ))}
                    </div>
                    <div className="mt-1.5 flex items-center justify-between text-xs">
                      <span style={{ color: ["#8A2A17", "#B47A1B", "#4C7A3D", "#1A3626"][pwStrength.score], fontWeight: 600 }}>
                        {pwStrength.label}
                      </span>
                      {pwStrength.feedback.length > 0 && pwStrength.score < 3 && (
                        <span style={{ color: "var(--sl-muted)" }}>{pwStrength.feedback[0]}</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
            <button data-testid="reg-continue-face" className="btn-primary mt-8 inline-flex items-center gap-2">
              Continue to face verification <ArrowRight size={16} />
            </button>
          </form>
        )}

        {/* Step 3: face verification */}
        {step === 3 && (
          <div className="u-card p-8 mt-8" data-testid="reg-step-face">
            <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Face verification</label>
            <p className="mt-2 text-sm" style={{ color: "var(--sl-muted)" }}>
              Your camera is used to detect facial landmarks on-device (MediaPipe) and compute a compact geometric
              descriptor -- checked against other registered accounts to catch duplicate signups. Only that small
              descriptor is sent to our server; the image/video never leaves your browser. This doesn't include
              liveness detection, so treat it as a duplicate-account check, not full biometric security.
            </p>

            <div className="mt-5 rounded-lg overflow-hidden border" style={{ borderColor: "var(--sl-border)", background: "#111", maxWidth: 420 }}>
              {faceStatus !== "verified" && (
                <video ref={videoRef} muted playsInline className="w-full h-auto block" />
              )}
              {faceStatus === "verified" && capturedFrame && (
                <img src={capturedFrame} alt="Captured face" className="w-full h-auto block" />
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />

            {cameraError && (
              <div className="mt-3 text-xs" style={{ color: "#B45309" }}>{cameraError}</div>
            )}

            <div className="mt-6 flex items-center gap-3">
              {faceStatus === "streaming" && (
                <button data-testid="reg-capture-face" onClick={captureAndVerify} className="btn-primary">
                  Capture & verify face
                </button>
              )}
              {faceStatus === "capturing" && (
                <button disabled className="btn-primary opacity-70">Verifying…</button>
              )}
              {faceStatus === "verified" && (
                <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--sl-primary)" }}>
                  <CheckCircle2 size={18} /> Face verified
                </div>
              )}
              {faceStatus !== "verified" && (
                <button data-testid="reg-skip-face" onClick={skipFace} className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }}>
                  Skip for now
                </button>
              )}
            </div>

            {faceStatus === "verified" && (
              <div className="mt-6 pt-6 border-t" style={{ borderColor: "var(--sl-border)" }}>
                {!showIris && irisStatus === "idle" && (
                  <button data-testid="reg-offer-iris" onClick={() => setShowIris(true)}
                          className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-accent)" }}>
                    + Add enhanced biometric security (simulated iris scan)
                  </button>
                )}

                {showIris && (
                  <div className="mt-3">
                    <div className="text-xs" style={{ color: "var(--sl-muted)" }}>
                      The iris is really detected live via an on-device ML model (MediaPipe) — nothing is
                      uploaded. The final "match" decision is simulated, since real biometric authentication
                      needs an enrolled template and infrared sensor hardware not available on laptop webcams.
                    </div>

                    <div className="mt-3 flex items-center gap-4">
                      <div className="relative h-[140px] w-[140px] rounded-full overflow-hidden flex items-center justify-center"
                           style={{ border: "2px solid var(--sl-border)", background: "#111" }}>
                        <video ref={irisVideoRef} muted playsInline className="hidden" />
                        <canvas ref={irisCanvasRef}
                                className={irisStatus === "scanning" || irisStatus === "verified" ? "w-full h-full object-cover" : "hidden"} />
                        {irisStatus === "idle" && <ScanFace size={28} style={{ color: "var(--sl-muted)" }} />}
                        {irisStatus === "loading" && <div className="text-[10px] text-center px-2" style={{ color: "var(--sl-muted)" }}>Loading iris model…</div>}
                      </div>

                      <div>
                        {irisStatus === "idle" && (
                          <button data-testid="reg-scan-iris" onClick={runIrisScan} className="btn-primary">Run iris scan</button>
                        )}
                        {irisStatus === "loading" && (
                          <div className="text-sm" style={{ color: "var(--sl-muted)" }}>Preparing camera and model…</div>
                        )}
                        {irisStatus === "scanning" && (
                          <div className="text-sm" style={{ color: "var(--sl-muted)" }}>{irisHint || "Locking on…"}</div>
                        )}
                        {irisStatus === "verified" && (
                          <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--sl-primary)" }}>
                            <CheckCircle2 size={18} /> Iris detected & matched (simulated)
                          </div>
                        )}
                        {irisStatus === "error" && (
                          <div className="text-sm" style={{ color: "#B45309" }}>{irisHint}</div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {faceStatus === "verified" && (
              <button data-testid="reg-submit" disabled={busy} onClick={submit} className="btn-primary mt-8 inline-flex items-center gap-2">
                {busy ? "Creating…" : "Create account"} <ArrowRight size={16} />
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}