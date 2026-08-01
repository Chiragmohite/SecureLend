# SecureLend — Product Requirements Document

## Original Problem Statement
Build **SecureLend**, an AI-powered NBFC digital loan platform with a built-in Hybrid Intrusion Detection System (IDS). Demonstration/academic project combining Fintech + Agentic AI + Cybersecurity. Two portals: User Portal (registration, KYC via phone-OTP & PAN, bank linking with consent, loan application with explainable AI decision) and Admin/Security Dashboard (live intrusion detection monitoring, attack logs, blocked IPs, loan/user management, Security Demo panel).

## Tech Choices (confirmed by user)
- Backend: **FastAPI + MongoDB** (adapted from Node/MySQL brief)
- Frontend: React + Tailwind + Recharts + Framer Motion + shadcn
- Auth: **Custom JWT + bcrypt**
- ML: **scikit-learn IsolationForest** for anomaly detection + explainable weighted rule-based loan scoring
- Attack simulation: **Security Demo panel with one-click triggers**
- Seed data: 10 users, 8 loans, ~50 attack logs, 3 blocked IPs

## User Personas
1. **NBFC Customer** — completes KYC, connects bank (consent), applies for loan, views transparent decision
2. **Security Analyst / Admin** — monitors live attack feed, manages blocked IPs, overrides loan decisions, triggers demo attacks

## Core Requirements (static)
- Phone-OTP verification + PAN regex validation
- Bank connection with explicit consent screen + timestamp
- Loan scoring engine with 5 explainable factors (income-to-loan, balance, employment, obligation headroom, KYC)
- Hybrid IDS: Rule engine (SQLi, brute force, unauthorized admin, malicious upload, XSS, rate limit) + statistical anomaly detection (IsolationForest)
- Admin SOC dashboard with charts, live feed, blocked IPs, users, loans, demo panel

## What's Been Implemented (2026-02-21)
- Backend: FastAPI server with JWT auth, brute-force lockout, IDS ASGI middleware, IsolationForest baseline, loan scoring, demo attack simulator, admin endpoints
- Seeded: admin + 10 demo users + 8 loans + 50 attacks + 3 blocked IPs
- Frontend: Landing, Register (3-step stepper), Login, User Dashboard, Bank Connect (with consent modal), Loan Apply (with explainable result card), Admin SOC Dashboard (6 tabs: Overview, Attack Feed, Blocked IPs, Users, Loans, Security Demo)
- Design: Dual identity — Organic/Earthy for user portal (Playfair + Manrope) vs Tactical Dark for admin SOC (JetBrains Mono + IBM Plex Sans)

## Backlog (not yet implemented / P1)
- WebSocket-based real-time feed (currently 8s polling)
- Downloadable audit report PDF for each loan decision
- Multi-factor auth (TOTP) for admin
- Email notifications on loan approval
- Loan tenure & EMI calculator on frontend

## Endpoints (auth)
- POST /api/auth/register, POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me
- POST /api/otp/send, POST /api/otp/verify, POST /api/kyc/pan-check
- GET /api/bank/list, POST /api/bank/connect, GET /api/bank/status
- POST /api/loans/apply, GET /api/loans/me
- GET /api/admin/stats, GET /api/admin/attacks, GET /api/admin/blocked-ips
- POST /api/admin/blocked-ips/{ip}/unblock
- GET /api/admin/users, GET /api/admin/loans, POST /api/admin/loans/{id}/override
- POST /api/admin/demo/attack
