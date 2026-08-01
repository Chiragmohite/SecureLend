# SecureLend

An AI-powered loan application platform with real-time explainable credit
scoring and a built-in intrusion detection system (IDS).

## What it does

- **KYC onboarding** — phone OTP, PAN verification, simulated bank
  connection, and geometric face-duplicate detection (catches the same
  person registering multiple accounts, using on-device MediaPipe
  landmarks — see `frontend/src/lib/faceEmbedding.js`).
- **Loan applications**, either via a structured form or a conversational
  chat flow, both running through the same scoring engine.
- **Explainable AI decisioning** (`backend/scoring.py`) — every decision
  breaks down into six weighted, human-readable factors (affordability,
  bank balance stability, employment stability, obligation headroom,
  income consistency, KYC completeness), plus hard-cap overrides for
  unaffordable FOIR or income mismatches that can't be laundered away by
  an otherwise-good score.
- **Salary slip OCR cross-check** — uploaded income proof is actually read
  (via Tesseract OCR + a regex heuristic) and the declared salary is
  checked against what the document says, not just whether a
  document-shaped file was uploaded.
- **Hybrid IDS** (`backend/ids.py`, `backend/server.py`) — a middleware
  pipeline combining rule-based detection (SQLi/XSS signatures, rate
  limiting, brute-force login lockouts, unauthorized-admin-route access)
  with a trained ML layer (Random Forest classifier + IsolationForest
  anomaly detector, trained on ~31k synthetic samples — see
  `backend/ml/model_card.json`).
- **Admin "SOC" dashboard** — live attack feed, blocked-IP management,
  user/loan overview, all polling in near real time.

## Tech stack

- **Backend:** FastAPI, MongoDB (Motor/async), scikit-learn, pytesseract,
  JWT auth, bcrypt.
- **Frontend:** React (CRA + craco), Tailwind CSS, MediaPipe Tasks Vision
  (face landmarks), Framer Motion.

## Local setup

### Backend

```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt --break-system-packages
```

Create `backend/.env` with:

```
MONGO_URL=your_mongodb_connection_string
DB_NAME=securelend
JWT_SECRET=a_long_random_secret
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=choose_a_password
DEMO_USER_EMAIL=demo@example.com
DEMO_USER_PASSWORD=choose_a_password
CORS_ORIGINS=http://localhost:3000
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_real_gmail_address
SMTP_PASSWORD=your_16_char_gmail_app_password
SMTP_FROM_NAME=SecureLend
# TESSERACT_CMD only needed on Windows -- point it at your local
# tesseract.exe install; leave unset on Linux/Mac (uses PATH).
```

Seed demo/admin accounts, then run the server:

```bash
python seed.py
uvicorn server:app --reload
```

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env` with:

```
REACT_APP_BACKEND_URL=http://localhost:8000
```

```bash
npm start
```

## Deployment

The backend ships with a `Dockerfile` that installs the real Tesseract
OCR binary (required for the salary-slip cross-check — most PaaS Python
buildpacks, including Render's default one, don't include it). Deploy the
backend as a Docker web service, and the frontend as a static site, with
`REACT_APP_BACKEND_URL` pointed at the deployed backend and `CORS_ORIGINS`
pointed at the deployed frontend.

## Known limitations (by design, not oversights)

- **Bank connection is simulated** — no real banking API integration;
  monthly income/balance are randomly generated per connection.
- **Face verification is a geometric duplicate-check, not production
  biometric security** — no liveness/anti-spoof detection, and it's
  sensitive to pose/lighting/expression. See the disclaimer already
  surfaced in the Register flow's UI.
- **OCR salary extraction is a regex heuristic**, not a general-purpose
  document parser — unusual payslip layouts may not extract cleanly (it
  fails open, not closed, in that case).
- **"Manual Review" as a decision status has no admin follow-up workflow**
  currently — severe income mismatches are hard-rejected rather than
  left in that state for exactly this reason.