import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShieldCheck, LogOut, Landmark, CreditCard, TrendingUp, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function UserDashboard() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [bank, setBank] = useState(null);
  const [loans, setLoans] = useState([]);

  useEffect(() => {
    api.get("/bank/status").then(r => setBank(r.data && Object.keys(r.data).length ? r.data : null));
    api.get("/loans/me").then(r => setLoans(r.data));
  }, []);

  const doLogout = async () => { await logout(); nav("/", { replace: true }); };

  return (
    <div className="user-portal min-h-screen">
      <header className="border-b" style={{ borderColor: "var(--sl-border)", background: "rgba(249,249,246,0.85)", backdropFilter: "blur(12px)" }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4">
          <Link to="/" className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
              <ShieldCheck className="text-white" size={18} />
            </div>
            <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
          </Link>
          <div className="flex items-center gap-4">
            <span className="text-sm" style={{ color: "var(--sl-muted)" }} data-testid="ud-hello">
              Hi, <span className="font-semibold" style={{ color: "var(--sl-primary)" }}>{user?.full_name?.split(" ")[0]}</span>
            </span>
            <button onClick={doLogout} className="btn-outline-user inline-flex items-center gap-2" data-testid="ud-logout">
              <LogOut size={14}/> Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        <h1 className="font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>Your loan workspace</h1>
        <p className="mt-2" style={{ color: "var(--sl-muted)" }}>Verify, connect, apply. Track every decision here.</p>

        <div className="grid md:grid-cols-3 gap-6 mt-8">
          {/* KYC */}
          <div className="u-card p-6" data-testid="ud-kyc-card">
            <div className="flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>
              <ShieldCheck size={14} /> KYC status
            </div>
            <div className="mt-4 space-y-2 text-sm">
              <Row ok={user?.phone_verified}>Mobile verified · +91-{user?.phone}</Row>
              <Row ok={user?.pan_verified}>PAN verified · {user?.pan}</Row>
              <Row ok={!!bank}>Bank {bank ? `linked · ${bank.bank_name}` : "not linked"}</Row>
            </div>
          </div>

          {/* Bank */}
          <div className="u-card p-6" data-testid="ud-bank-card">
            <div className="flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>
              <Landmark size={14} /> Bank account
            </div>
            {bank ? (
              <>
                <div className="mt-4 font-serif text-xl" style={{ color: "var(--sl-primary)" }}>{bank.bank_name}</div>
                <div className="text-sm font-mono mt-1" style={{ color: "var(--sl-muted)" }}>{bank.account_masked}</div>
                <div className="grid grid-cols-2 gap-3 mt-4">
                  <Stat label="Monthly income" value={`₹${bank.monthly_income.toLocaleString()}`} />
                  <Stat label="Avg. balance" value={`₹${Math.round(bank.avg_balance).toLocaleString()}`} />
                </div>
              </>
            ) : (
              <>
                <p className="mt-4 text-sm" style={{ color: "var(--sl-muted)" }}>Connect your bank to unlock AI eligibility scoring.</p>
                <Link to="/app/bank" className="btn-primary mt-6 inline-flex items-center gap-2" data-testid="ud-connect-bank">Connect bank <ArrowRight size={14}/></Link>
              </>
            )}
          </div>

          {/* Apply */}
          <div className="u-card p-6 relative overflow-hidden" data-testid="ud-apply-card">
            <div className="flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>
              <CreditCard size={14}/> Loan application
            </div>
            <p className="mt-4 text-sm" style={{ color: "var(--sl-muted)" }}>Tell us what you need. Get a transparent AI decision instantly.</p>
            <Link to="/app/loan" className="btn-accent mt-6 inline-flex items-center gap-2" data-testid="ud-apply-btn">Start application <ArrowRight size={14}/></Link>
          </div>
        </div>

        {/* Loans list */}
        <div className="u-card mt-10 overflow-hidden" data-testid="ud-loans">
          <div className="px-6 py-5 flex items-center justify-between" style={{ borderBottom: "1px solid var(--sl-border)" }}>
            <div className="flex items-center gap-2">
              <TrendingUp size={16} style={{ color: "var(--sl-primary)" }}/>
              <span className="font-serif text-xl" style={{ color: "var(--sl-primary)" }}>Your applications</span>
            </div>
            <Link to="/app/loan" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-accent)" }} data-testid="ud-new-loan">+ New application</Link>
          </div>
          {loans.length === 0 ? (
            <div className="px-6 py-12 text-center text-sm" style={{ color: "var(--sl-muted)" }}>No applications yet.</div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>
                  <th className="text-left px-6 py-3">Amount</th>
                  <th className="text-left px-6 py-3">Purpose</th>
                  <th className="text-left px-6 py-3">Score</th>
                  <th className="text-left px-6 py-3">Risk</th>
                  <th className="text-left px-6 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {loans.map((l) => (
                  <tr key={l.id} className="text-sm" style={{ borderTop: "1px solid var(--sl-border)" }} data-testid={`ud-loan-${l.id}`}>
                    <td className="px-6 py-4 font-serif text-lg" style={{ color: "var(--sl-primary)" }}>₹{l.loan_amount.toLocaleString()}</td>
                    <td className="px-6 py-4">{l.purpose}</td>
                    <td className="px-6 py-4 font-mono">{l.eligibility_score}</td>
                    <td className="px-6 py-4">
                      <span className="chip" style={{
                        background: l.risk_level === "LOW" ? "#E4EFE7" : l.risk_level === "MEDIUM" ? "#FBEDD9" : "#F7DDD5",
                        color: l.risk_level === "LOW" ? "#1A3626" : l.risk_level === "MEDIUM" ? "#7A5410" : "#8A2A17"
                      }}>{l.risk_level}</span>
                    </td>
                    <td className="px-6 py-4 font-semibold" style={{
                      color: l.loan_status === "Approved" ? "#1A3626" : l.loan_status === "Rejected" ? "#8A2A17" : "#7A5410"
                    }}>{l.loan_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}

function Row({ ok, children }) {
  return (
    <div className="flex items-center gap-3">
      <span className="h-2 w-2 rounded-full inline-block" style={{ background: ok ? "var(--sl-primary)" : "#D5B7A6" }} />
      <span style={{ color: "var(--sl-text)" }}>{children}</span>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>{label}</div>
      <div className="font-serif text-lg" style={{ color: "var(--sl-primary)" }}>{value}</div>
    </div>
  );
}
