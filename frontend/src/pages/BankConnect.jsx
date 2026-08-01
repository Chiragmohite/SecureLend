import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, Landmark, ArrowRight, Lock, CheckCircle2 } from "lucide-react";
import api, { formatApiErrorDetail } from "@/lib/api";

export default function BankConnect() {
  const [banks, setBanks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showConsent, setShowConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [accountNumber, setAccountNumber] = useState("");
  const [ifsc, setIfsc] = useState("");
  const nav = useNavigate();

  useEffect(() => { api.get("/bank/list").then(r => setBanks(r.data)); }, []);

  const accountValid = /^\d{9,18}$/.test(accountNumber);

  const openConsent = (b) => {
    setSelected(b);
    setAccountNumber("");
    setIfsc("");
    setShowConsent(true);
  };

  const connect = async () => {
    setBusy(true);
    try {
      await api.post("/bank/connect", {
        bank_name: selected.code,
        consent: true,
        account_number: accountNumber,
        ifsc_code: ifsc.toUpperCase(),
      });
      toast.success(`${selected.name} linked successfully`);
      nav("/app");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); setShowConsent(false); }
  };

  return (
    <div className="user-portal min-h-screen">
      <header className="max-w-4xl mx-auto flex items-center justify-between px-6 py-5">
        <Link to="/app" className="flex items-center gap-2" data-testid="bc-brand">
          <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
            <ShieldCheck className="text-white" size={18} />
          </div>
          <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
        </Link>
        <Link to="/app" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }} data-testid="bc-back">← Back to dashboard</Link>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3">
          <Landmark size={24} style={{ color: "var(--sl-accent)" }} />
          <h1 className="font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>Connect your bank</h1>
        </div>
        <p className="mt-2" style={{ color: "var(--sl-muted)" }}>We use bank data only to underwrite your loan. Read-only, revocable, encrypted in transit.</p>

        <div className="grid grid-cols-2 gap-4 mt-10">
          {banks.map((b) => (
            <button
              key={b.code}
              onClick={() => openConsent(b)}
              className="u-card p-6 flex items-center justify-between transition-transform hover:-translate-y-0.5"
              style={{ background: "#FFF" }}
              data-testid={`bc-bank-${b.code}`}
            >
              <div className="text-left">
                <div className="font-serif text-2xl" style={{ color: "var(--sl-primary)" }}>{b.name}</div>
                <div className="text-xs mt-1" style={{ color: "var(--sl-muted)" }}>Read-only account & income verification</div>
              </div>
              <ArrowRight size={18} style={{ color: "var(--sl-accent)" }} />
            </button>
          ))}
        </div>
      </main>

      {/* Consent modal */}
      {showConsent && selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" style={{ background: "rgba(18,34,23,0.55)" }}>
          <div className="u-card max-w-lg w-full p-8" data-testid="bc-consent-modal">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full flex items-center justify-center" style={{ background: "#EAF1EC" }}>
                <Lock size={18} style={{ color: "var(--sl-primary)" }}/>
              </div>
              <div>
                <div className="font-serif text-xl" style={{ color: "var(--sl-primary)" }}>Consent for {selected.name}</div>
                <div className="text-xs" style={{ color: "var(--sl-muted)" }}>Purpose: Loan eligibility verification</div>
              </div>
            </div>

            <div className="mt-6 space-y-3 text-sm">
              <ConsentItem>Read your <b>account holder name</b> for identity match.</ConsentItem>
              <ConsentItem>Read your <b>monthly income</b> credit patterns.</ConsentItem>
              <ConsentItem>Read your <b>transaction summary</b> and average balance.</ConsentItem>
              <ConsentItem>Consent is <b>revocable</b> at any time from your dashboard.</ConsentItem>
            </div>

            <div className="mt-6">
              <label className="block text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Your account number</label>
              <input
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value.replace(/\D/g, "").slice(0, 18))}
                className="w-full mt-2 px-4 py-3 rounded-lg border font-mono outline-none focus:border-[var(--sl-primary)]"
                style={{ borderColor: "var(--sl-border)" }}
                placeholder="9-18 digit account number"
                data-testid="bc-account-number"
              />
              {accountNumber.length > 0 && !accountValid && (
                <div className="mt-1 text-xs" style={{ color: "#B45309" }}>Enter 9-18 digits.</div>
              )}

              <label className="block mt-4 text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>IFSC code</label>
              <input
                value={ifsc}
                onChange={(e) => setIfsc(e.target.value.toUpperCase().slice(0, 11))}
                className="w-full mt-2 px-4 py-3 rounded-lg border font-mono tracking-widest outline-none focus:border-[var(--sl-primary)]"
                style={{ borderColor: "var(--sl-border)" }}
                placeholder="e.g. SBIN0001234"
                data-testid="bc-ifsc"
              />
            </div>

            <div className="mt-6 text-xs p-3 rounded-lg" style={{ background: "#F5F6F0", color: "var(--sl-muted)" }}>
              This is a simulated flow. Your account number is used only to display a masked reference (last 4 digits) — no real bank credentials are collected or verified. Timestamp of consent is logged.
            </div>

            <div className="mt-6 flex gap-3">
              <button className="btn-outline-user flex-1" onClick={() => setShowConsent(false)} data-testid="bc-consent-cancel">Cancel</button>
              <button className="btn-primary flex-1" disabled={busy || !accountValid} onClick={connect} data-testid="bc-consent-allow">
                {busy ? "Linking…" : "Allow & Continue"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ConsentItem({ children }) {
  return (
    <div className="flex items-start gap-3">
      <CheckCircle2 size={16} style={{ color: "var(--sl-primary)", marginTop: 2 }}/>
      <div>{children}</div>
    </div>
  );
}