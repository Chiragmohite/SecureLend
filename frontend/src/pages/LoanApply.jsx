import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, CreditCard, ArrowRight, AlertTriangle } from "lucide-react";
import api, { formatApiErrorDetail } from "@/lib/api";

// How far a declared salary can diverge from bank-observed income before
// we show a warning in the UI (backend has its own independent hard cap --
// this is just an earlier, friendlier nudge before submission).
const SALARY_MISMATCH_WARN_RATIO = 0.85;

export const EMP_TYPES = [
  { key: "salaried", label: "Salaried" },
  { key: "self_employed", label: "Self-employed" },
  { key: "business", label: "Business owner" },
];

export const PURPOSES = ["Home Renovation", "Education", "Medical", "Wedding", "Business Expansion", "Debt Consolidation", "Travel", "Other"];

const TENURES = [12, 24, 36, 48, 60];

export default function LoanApply() {
  const nav = useNavigate();
  const [amount, setAmount] = useState(200000);
  const [emp, setEmp] = useState("salaried");
  const [salary, setSalary] = useState("");
  const [salaryTouched, setSalaryTouched] = useState(false);
  const [bankIncome, setBankIncome] = useState(null);
  const [emi, setEmi] = useState(0);
  const [tenure, setTenure] = useState(36);
  const [purpose, setPurpose] = useState(PURPOSES[0]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  // Prefill declared salary from the applicant's verified bank-observed
  // income, so the default isn't just a random guess -- they can still
  // edit it (e.g. a raise the bank data hasn't caught up to yet), but
  // starting from real data instead of a blank/arbitrary number.
  useEffect(() => {
    api.get("/bank/status").then((r) => {
      const income = r.data?.monthly_income;
      if (income) {
        setBankIncome(income);
        setSalary((prev) => (prev === "" ? income : prev));
      }
    }).catch(() => {});
  }, []);

  const salaryNum = Number(salary) || 0;
  const mismatchRatio = bankIncome && salaryNum
    ? Math.min(bankIncome, salaryNum) / Math.max(bankIncome, salaryNum)
    : 1;
  const showMismatchWarning = salaryTouched && bankIncome && mismatchRatio < SALARY_MISMATCH_WARN_RATIO;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/loans/apply", {
        loan_amount: Number(amount),
        employment_type: emp,
        monthly_salary: Number(salary),
        existing_emi: Number(emi),
        purpose,
        tenure_months: Number(tenure),
      });
      setResult(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="user-portal min-h-screen">
      <header className="max-w-5xl mx-auto flex items-center justify-between px-6 py-5">
        <Link to="/app" className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
            <ShieldCheck className="text-white" size={18} />
          </div>
          <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
        </Link>
        <Link to="/app" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }}>← Back</Link>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3">
          <CreditCard size={24} style={{ color: "var(--sl-accent)" }}/>
          <h1 className="font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>New loan application</h1>
        </div>
        <p className="mt-2" style={{ color: "var(--sl-muted)" }}>Real-time AI scoring. You'll see the reasoning, interest rate, and EMI immediately.</p>
        {!result && (
          <Link to="/app/loan/chat" className="inline-block mt-4 text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-accent)" }} data-testid="la-switch-chat">
            Prefer to apply by chat instead? →
          </Link>
        )}

        {!result ? (
          <form onSubmit={submit} className="u-card p-8 mt-8" data-testid="la-form">
            <div className="grid md:grid-cols-2 gap-5">
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Loan amount (₹)</label>
                <input required data-testid="la-amount" type="number" min="10000" step="1000" value={amount} onChange={(e)=>setAmount(e.target.value)}
                       className="w-full mt-2 px-4 py-3 rounded-lg border font-mono outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} />
                <div className="mt-3 flex gap-2 flex-wrap">
                  {[50000, 100000, 250000, 500000, 1000000].map((v) => (
                    <button key={v} type="button" onClick={()=>setAmount(v)} className="text-xs px-3 py-1 rounded-full border" style={{ borderColor: "var(--sl-border)", color: "var(--sl-primary)" }}>₹{v.toLocaleString()}</button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Employment type</label>
                <div className="grid grid-cols-3 gap-2 mt-2">
                  {EMP_TYPES.map((t) => (
                    <button key={t.key} type="button" onClick={()=>setEmp(t.key)}
                      className="px-3 py-2 rounded-lg text-sm border transition-colors"
                      style={{
                        background: emp === t.key ? "var(--sl-primary)" : "#FFF",
                        color: emp === t.key ? "#FFF" : "var(--sl-primary)",
                        borderColor: emp === t.key ? "var(--sl-primary)" : "var(--sl-border)"
                      }} data-testid={`la-emp-${t.key}`}>{t.label}</button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Loan tenure</label>
                <div className="grid grid-cols-5 gap-2 mt-2">
                  {TENURES.map((t) => (
                    <button key={t} type="button" onClick={()=>setTenure(t)}
                      className="px-2 py-2 rounded-lg text-xs border transition-colors"
                      style={{
                        background: tenure === t ? "var(--sl-primary)" : "#FFF",
                        color: tenure === t ? "#FFF" : "var(--sl-primary)",
                        borderColor: tenure === t ? "var(--sl-primary)" : "var(--sl-border)"
                      }} data-testid={`la-tenure-${t}`}>{t}mo</button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Monthly salary (₹)</label>
                <input required data-testid="la-salary" type="number" min="0" step="1000" value={salary}
                       onChange={(e)=>{ setSalary(e.target.value); setSalaryTouched(true); }}
                       className="w-full mt-2 px-4 py-3 rounded-lg border font-mono outline-none focus:border-[var(--sl-primary)]"
                       style={{ borderColor: showMismatchWarning ? "#B47A1B" : "var(--sl-border)" }} />
                {bankIncome ? (
                  <div className="mt-1.5 text-xs" style={{ color: "var(--sl-muted)" }}>
                    Bank-verified income: ₹{bankIncome.toLocaleString()}/mo
                  </div>
                ) : null}
                {showMismatchWarning && (
                  <div className="mt-2 flex items-start gap-1.5 text-xs" style={{ color: "#B47A1B" }} data-testid="la-salary-mismatch-warning">
                    <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                    <span>This differs noticeably from your bank-verified income (₹{bankIncome.toLocaleString()}/mo). A large enough mismatch will cause your application to be rejected.</span>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Existing EMI (₹/month)</label>
                <input data-testid="la-emi" type="number" min="0" step="500" value={emi} onChange={(e)=>setEmi(e.target.value)}
                       className="w-full mt-2 px-4 py-3 rounded-lg border font-mono outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }} />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Purpose</label>
                <select data-testid="la-purpose" value={purpose} onChange={(e)=>setPurpose(e.target.value)}
                        className="w-full mt-2 px-4 py-3 rounded-lg border bg-white outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)" }}>
                  {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </div>

            <button type="submit" disabled={busy} className="btn-primary mt-8 inline-flex items-center gap-2" data-testid="la-submit">
              {busy ? "Running AI decision…" : "Submit application"} <ArrowRight size={16}/>
            </button>
          </form>
        ) : (
          <ResultCard result={result} onNew={() => { setResult(null); }} onBack={() => nav("/app")} />
        )}
      </main>
    </div>
  );
}

export function ResultCard({ result, onNew, onBack }) {
  const color = result.risk_level === "LOW" ? "#1A3626" : result.risk_level === "MEDIUM" ? "#B47A1B" : "#8A2A17";
  const bg = result.loan_status === "Approved" ? "#EAF1EC" : result.loan_status === "Rejected" ? "#F7DDD5" : "#FBEDD9";
  return (
    <div className="u-card mt-8 p-8" data-testid="la-result">
      <div className="chip" style={{ background: bg, color }}>{result.loan_status} · Risk {result.risk_level}</div>
      <div className="mt-4 flex items-end gap-4">
        <div className="font-serif text-6xl" style={{ color: "var(--sl-primary)" }} data-testid="la-result-score">{result.eligibility_score}</div>
        <div className="pb-2" style={{ color: "var(--sl-muted)" }}>Eligibility score / 100</div>
      </div>

      <div className="mt-6 h-3 rounded-full" style={{ background: "#E9EBE3" }}>
        <div className="h-3 rounded-full" style={{ width: `${result.eligibility_score}%`, background: color }} />
      </div>

      {result.interest_rate_pa !== undefined && (
        <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
          <LoanStat label="Interest rate" value={`${result.interest_rate_pa}% p.a.`} />
          <LoanStat label="Tenure" value={`${result.tenure_months} months`} />
          <LoanStat label="Monthly EMI" value={`₹${result.monthly_emi?.toLocaleString()}`} highlight />
          <LoanStat label="Total interest" value={`₹${result.total_interest?.toLocaleString()}`} />
        </div>
      )}

      <div className="mt-8">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Explainable factors</div>
        <div className="mt-3 space-y-3">
          {result.factors.map((f) => (
            <div key={f.name} className="flex items-center gap-4">
              <div className="w-56 text-sm">{f.name}</div>
              <div className="flex-1 h-2 rounded-full" style={{ background: "#EFF1E9" }}>
                <div className="h-2 rounded-full" style={{ width: `${(f.score / f.weight) * 100}%`, background: "var(--sl-primary)" }} />
              </div>
              <div className="w-28 text-right font-mono text-xs" style={{ color: "var(--sl-muted)" }}>{f.score} / {f.weight}</div>
              <div className="w-56 text-xs" style={{ color: "var(--sl-muted)" }}>{f.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {result.suggested_amount > 0 && result.loan_status !== "Approved" && (
        <div className="mt-6 p-4 rounded-lg text-sm" style={{ background: "#F5F6F0", color: "var(--sl-text)" }}>
          Based on your obligations we could pre-approve you up to <b>₹{result.suggested_amount.toLocaleString()}</b>. Try adjusting the amount.
        </div>
      )}

      {result.loan_status === "Approved" && result.total_repayment !== undefined && (
        <div className="mt-6 p-4 rounded-lg text-sm" style={{ background: "#F5F6F0", color: "var(--sl-text)" }}>
          Total repayment over {result.tenure_months} months: <b>₹{result.total_repayment.toLocaleString()}</b> (principal ₹{result.loan_amount?.toLocaleString?.() ?? ""} + interest ₹{result.total_interest.toLocaleString()}).
        </div>
      )}

      <div className="mt-8 flex gap-3">
        <button className="btn-outline-user" onClick={onNew} data-testid="la-result-new">Try different terms</button>
        <button className="btn-primary" onClick={onBack} data-testid="la-result-done">Back to dashboard</button>
      </div>
    </div>
  );
}

function LoanStat({ label, value, highlight }) {
  return (
    <div className="p-4 rounded-lg" style={{ background: highlight ? "#EAF1EC" : "#F5F6F0" }}>
      <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>{label}</div>
      <div className="mt-1 font-serif text-xl" style={{ color: "var(--sl-primary)" }}>{value}</div>
    </div>
  );
}