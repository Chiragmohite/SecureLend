"""Transparent, explainable loan scoring engine.

v3 — adds risk-based interest rate pricing on top of v2's fixes:

v2 fixed two problems:
1. Scoring now uses the applicant's *declared* income (not just a random
   "bank-observed" figure), and separately checks the two against each
   other as a consistency/fraud signal.
2. Hard gates (not just a weighted average) catch catastrophic single
   factors -- e.g. a loan that isn't serviceable from declared income is
   rejected outright, regardless of how good other factors look.

v3 adds: a flat 14% p.a. for everyone isn't how real lenders price risk.
This version prices the interest rate from the applicant's non-debt
profile (balance stability, employment, income consistency, KYC) *before*
computing the loan's own EMI, then checks affordability at that priced
rate. This avoids circularity (rate depends on risk; risk depends on the
size of the EMI, which depends on the rate) by only pricing off factors
that don't depend on the requested loan itself.

Factors (weights sum to 100):
 - loan_affordability      (35): FOIR -- (existing_emi + estimated EMI of
                                  the requested loan, AT THE PRICED RATE)
                                  / declared monthly income
 - bank_balance_stability  (20): avg_balance vs bank-observed monthly income
 - employment_stability    (15): salaried > business > self_employed
 - obligation_headroom     (10): existing EMI burden alone, excluding this loan
 - income_consistency      (15): declared income vs bank-observed income
 - kyc_completeness        (5):  phone + PAN + bank (+ income proof, when
                                  required for large loans -- see server.py)

Interest rate tiers (priced off the non-debt-dependent 65 points above,
i.e. everything except loan_affordability itself):
 - proxy >= 85% -> 10.5% p.a.  ("excellent" profile)
 - proxy >= 65% -> 13.0% p.a.  ("good")
 - proxy >= 45% -> 16.0% p.a.  ("fair")
 - else         -> 20.0% p.a.  ("weak" -- still priced, may still fail FOIR gate)
(Illustrative tiers only -- a real product would calibrate these against
actual default-rate data, not fixed guesses. State this in your report.)

Hard gates (override the weighted total regardless of score):
 - FOIR > 65%                      -> HIGH risk, Rejected (loan is not
                                       serviceable from declared income at
                                       any reasonable weighting of other factors)
 - Declared vs bank income mismatch
   ratio < 0.85                    -> capped at Manual Review (income cannot
                                       be auto-trusted enough to auto-approve,
                                       even if everything else scores well)

Assumptions made explicit here (state these in your report):
 - EMI uses the standard reducing-balance formula
 - tenure_months is a required input from the applicant, not assumed
 - Interest rate tiers above are illustrative, not derived from real
   default data (no such data exists for a demo project)
"""
from typing import Dict, Any

FOIR_HARD_REJECT = 0.65      # >65% of income going to EMIs: not serviceable
FOIR_FULL_MARKS = 0.35       # <=35%: comfortable, full marks on affordability
INCOME_MISMATCH_HARD_CAP = 0.85  # declared vs bank income ratio below this: cap at Manual Review
# (aligned with the frontend's SALARY_MISMATCH_WARN_RATIO in LoanApply.jsx /
# LoanApplyChat.jsx -- previously this was 0.75 while the frontend warned at
# 0.85, so a mismatch like 80k declared vs 65k bank-observed (ratio 0.81)
# triggered the warning message but the backend still auto-approved it
# anyway. Keeping these two numbers equal means "this may go to manual
# review" is only ever shown when it's actually true.)

RATE_TIERS = [  # (min proxy_pct, annual_rate) -- checked highest first
    (0.85, 0.105),
    (0.65, 0.130),
    (0.45, 0.160),
    (0.00, 0.200),
]


def _pick_interest_rate(proxy_pct: float) -> float:
    for threshold, rate in RATE_TIERS:
        if proxy_pct >= threshold:
            return rate
    return RATE_TIERS[-1][1]


def _emi(principal: float, annual_rate: float, months: int) -> float:
    """Standard reducing-balance EMI. Falls back to a flat split if months<=0."""
    if months <= 0:
        return principal
    r = annual_rate / 12.0
    if r <= 0:
        return principal / months
    factor = (1 + r) ** months
    return principal * r * factor / (factor - 1)


def _max_principal_for_emi(max_emi: float, annual_rate: float, months: int) -> float:
    """Inverse of _emi: largest principal serviceable at a given EMI ceiling."""
    if max_emi <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r <= 0:
        return max_emi * months
    factor = (1 + r) ** months
    return max_emi * (factor - 1) / (r * factor)


def score_loan(*, declared_monthly_income: float, bank_monthly_income: float, avg_balance: float,
               employment_type: str, loan_amount: float, existing_emi: float,
               tenure_months: int, kyc_flags: Dict[str, bool],
               slip_monthly_income: float | None = None) -> Dict[str, Any]:
    declared_monthly_income = max(0.0, declared_monthly_income)
    bank_monthly_income = max(0.0, bank_monthly_income)

    # ---- Step 1: score the non-debt-dependent factors first (these don't
    # depend on the requested loan's own EMI, so no circularity) ----

    # Balance stability (against bank-observed income, since that's what the
    # balance figure was actually generated/observed relative to)
    if bank_monthly_income <= 0:
        r2 = 0.0
    else:
        bal_ratio = avg_balance / bank_monthly_income
        r2 = max(0.0, min(1.0, bal_ratio / 1.5))

    # Employment
    emp_map = {"salaried": 1.0, "business": 0.75, "self_employed": 0.55}
    r3 = emp_map.get(employment_type, 0.5)

    # Existing obligation headroom (pre-existing EMIs only, excluding this loan)
    if declared_monthly_income <= 0:
        r4 = 0.0
    else:
        headroom = max(0.0, (declared_monthly_income - existing_emi) / declared_monthly_income)
        r4 = min(1.0, headroom / 0.7)

    # Income consistency: declared vs every verified income source we have
    # (bank-observed, and the salary slip's printed figure if OCR could
    # extract one). Uses the *worst* (most restrictive) mismatch ratio
    # across sources -- a declared income only needs to disagree badly with
    # ONE verified source to be a red flag, not all of them.
    verified_incomes = [("bank-observed", bank_monthly_income)]
    if slip_monthly_income and slip_monthly_income > 0:
        verified_incomes.append(("salary slip", slip_monthly_income))

    if declared_monthly_income <= 0:
        income_mismatch_ratio = 0.0
        worst_source = None
    else:
        ratios = [
            (label, min(declared_monthly_income, inc) / max(declared_monthly_income, inc))
            for label, inc in verified_incomes if inc > 0
        ]
        if ratios:
            worst_source, income_mismatch_ratio = min(ratios, key=lambda x: x[1])
        else:
            income_mismatch_ratio, worst_source = 0.0, None
    r5 = max(0.0, min(1.0, (income_mismatch_ratio - INCOME_MISMATCH_HARD_CAP) / (0.98 - INCOME_MISMATCH_HARD_CAP)))

    # KYC completeness
    kyc_count = sum(1 for v in kyc_flags.values() if v)
    r6 = kyc_count / max(1, len(kyc_flags))

    # ---- Step 2: price the interest rate off those factors ----
    non_debt_weight = 20 + 15 + 10 + 15 + 5  # 65
    non_debt_points = r2 * 20 + r3 * 15 + r4 * 10 + r5 * 15 + r6 * 5
    proxy_pct = non_debt_points / non_debt_weight
    interest_rate = _pick_interest_rate(proxy_pct)

    # ---- Step 3: NOW compute affordability at the priced rate ----
    requested_emi = _emi(loan_amount, interest_rate, tenure_months) if loan_amount > 0 else 0.0
    foir = ((existing_emi + requested_emi) / declared_monthly_income) if declared_monthly_income > 0 else 1.0
    r1 = max(0.0, min(1.0, 1 - (foir - FOIR_FULL_MARKS) / (FOIR_HARD_REJECT - FOIR_FULL_MARKS)))

    factors = [
        {
            "name": "Loan Affordability",
            "weight": 35,
            "score": round(r1 * 35, 1),
            "detail": (f"Est. EMI ₹{requested_emi:,.0f}/mo over {tenure_months}mo at "
                       f"{interest_rate*100:.1f}% p.a. = {foir*100:.0f}% of declared income "
                       f"(₹{declared_monthly_income:,.0f}/mo)"),
        },
        {
            "name": "Bank Balance Stability",
            "weight": 20,
            "score": round(r2 * 20, 1),
            "detail": f"Avg balance ₹{avg_balance:,.0f} = {r2*1.5:.1f}x bank-observed monthly income",
        },
        {
            "name": "Employment Stability",
            "weight": 15,
            "score": round(r3 * 15, 1),
            "detail": f"Type: {employment_type.replace('_', ' ').title()}",
        },
        {
            "name": "Existing Obligation Headroom",
            "weight": 10,
            "score": round(r4 * 10, 1),
            "detail": f"Existing EMI: ₹{existing_emi:,.0f}/mo before this loan",
        },
        {
            "name": "Income Consistency",
            "weight": 15,
            "score": round(r5 * 15, 1),
            "detail": (
                f"Declared ₹{declared_monthly_income:,.0f}/mo vs bank-observed ₹{bank_monthly_income:,.0f}/mo"
                + (f", salary slip shows ₹{slip_monthly_income:,.0f}/mo" if slip_monthly_income else "")
            ),
        },
        {
            "name": "KYC Completeness",
            "weight": 5,
            "score": round(r6 * 5, 1),
            "detail": f"{kyc_count}/{len(kyc_flags)} checks completed",
        },
    ]

    eligibility = round(sum(f["score"] for f in factors), 1)
    risk_override_reason = None

    if foir > FOIR_HARD_REJECT:
        risk, decision = "HIGH", "Rejected"
        risk_override_reason = (
            f"Hard affordability gate: at your priced rate of {interest_rate*100:.1f}% p.a., the "
            f"estimated EMI would consume {foir*100:.0f}% of declared income "
            f"(limit {FOIR_HARD_REJECT*100:.0f}%) -- rejected regardless of other factors."
        )
    elif income_mismatch_ratio < INCOME_MISMATCH_HARD_CAP:
        # Outright reject rather than "Manual Review" -- this app has no
        # admin workflow that actually acts on manual-review applications,
        # so leaving one there would just be a permanent dead end for the
        # applicant. A severe, verified income mismatch is rejected
        # regardless of how the weighted score alone would have come out.
        risk, decision = "HIGH", "Rejected"
        source_note = f" ({worst_source} income)" if worst_source else ""
        risk_override_reason = (
            f"Hard cap: declared income diverges too far from verified income{source_note} "
            "-- rejected regardless of the weighted score, pending resubmission with "
            "accurate income details."
        )
    elif eligibility >= 70:
        risk, decision = "LOW", "Approved"
    elif eligibility >= 50:
        risk, decision = "MEDIUM", "Manual Review"
    else:
        risk, decision = "HIGH", "Rejected"

    # Suggested loan amount: largest principal serviceable at a 35% FOIR
    # ceiling on declared income, at the priced rate and requested tenure.
    max_emi = max(0.0, declared_monthly_income * FOIR_FULL_MARKS - existing_emi)
    suggested = round(_max_principal_for_emi(max_emi, interest_rate, tenure_months), -3)

    return {
        "eligibility_score": eligibility,
        "risk_level": risk,
        "decision": decision,
        "factors": factors,
        "suggested_amount": suggested,
        "risk_override_reason": risk_override_reason,
        "estimated_emi": round(requested_emi, 0),
        "interest_rate": interest_rate,
    }