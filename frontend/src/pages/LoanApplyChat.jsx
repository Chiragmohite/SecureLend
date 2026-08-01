import { useState, useRef, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, Send, Upload } from "lucide-react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { ResultCard, EMP_TYPES, PURPOSES } from "./LoanApply";

/**
 * LoanApplyChat.jsx
 * ------------------
 * A rule-based conversational loan application flow. This is a deliberate
 * design choice: it's a finite state machine (not an LLM), so it costs
 * nothing to run, needs no API key, and is fully deterministic/testable --
 * appropriate for an academic project where "AI decisioning" already
 * happens at the scoring stage (scoring.py / the trained IDS model), not
 * in the chat itself. The chat here is a conversational INPUT METHOD for
 * the same /loans/apply endpoint the form uses, not a separate AI system.
 */

const FIELDS = [
  { key: "amount", prompt: "How much would you like to borrow? (e.g. 200000)", type: "number", min: 10000 },
  { key: "emp", prompt: "What's your employment type?", type: "buttons", options: EMP_TYPES.map(t => ({ value: t.key, label: t.label })) },
  { key: "salary", prompt: "What's your monthly income? (₹)", type: "number", min: 0 },
  { key: "emi", prompt: "Any existing EMI obligations per month? Enter 0 if none.", type: "number", min: 0 },
  { key: "purpose", prompt: "What's this loan for?", type: "buttons", options: PURPOSES.map(p => ({ value: p, label: p })) },
  { key: "tenure", prompt: "Last thing — over how many months would you like to repay it?", type: "buttons",
    options: [12, 24, 36, 48, 60].map(m => ({ value: m, label: `${m} months` })) },
];

const GREETING = "Hi! I'm the SecureLend loan assistant. I'll ask a few quick questions and run your application through our AI decision engine at the end. Ready?";

// Same friendly pre-submission nudge threshold as the form flow (LoanApply.jsx)
// -- the backend has its own independent hard cap that actually affects the
// decision; this is just an earlier heads-up in the conversation.
const SALARY_MISMATCH_WARN_RATIO = 0.85;

export default function LoanApplyChat() {
  const nav = useNavigate();
  const [messages, setMessages] = useState([{ from: "bot", text: GREETING }]);
  const [stepIdx, setStepIdx] = useState(-1); // -1 = waiting for "ready" confirmation
  const [answers, setAnswers] = useState({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [incomeProof, setIncomeProof] = useState(null); // { required_above, verified, filename }
  const [bankIncome, setBankIncome] = useState(null);
  const [awaitingProof, setAwaitingProof] = useState(false);
  const [uploadingProof, setUploadingProof] = useState(false);
  const [pendingAnswers, setPendingAnswers] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    api.get("/kyc/income-proof/status").then(({ data }) => setIncomeProof(data)).catch(() => {});
    api.get("/bank/status").then(({ data }) => setBankIncome(data?.monthly_income || null)).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, awaitingProof]);

  const pushBot = (text) => setMessages((m) => [...m, { from: "bot", text }]);
  const pushUser = (text) => setMessages((m) => [...m, { from: "user", text }]);

  const askNext = (nextIdx, latestAnswers) => {
    if (nextIdx >= FIELDS.length) {
      const needsProof = incomeProof && Number(latestAnswers.amount) >= incomeProof.required_above && !incomeProof.verified;
      if (needsProof) {
        setPendingAnswers(latestAnswers);
        setAwaitingProof(true);
        setStepIdx(nextIdx);
        setTimeout(() => pushBot(
          `Loans of ₹${incomeProof.required_above.toLocaleString()}+ need a salary slip / income proof upload before I can run the decision. Please upload one below.`
        ), 350);
        return;
      }
      runApplication(latestAnswers);
      return;
    }
    setStepIdx(nextIdx);
    const field = FIELDS[nextIdx];
    let prompt = field.prompt;
    if (field.key === "salary" && bankIncome) {
      prompt = `${field.prompt} (For reference, your bank-verified income is ₹${bankIncome.toLocaleString()}/mo.)`;
    }
    setTimeout(() => pushBot(prompt), 350);
  };

  const uploadProofAndContinue = async (file) => {
    if (!file) return;
    setUploadingProof(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.post("/kyc/income-proof", form, { headers: { "Content-Type": "multipart/form-data" } });
      setIncomeProof((p) => ({ ...p, verified: true, filename: file.name }));
      setAwaitingProof(false);
      pushUser(`Uploaded: ${file.name}`);
      pushBot("Got it, thanks — verified. Running your application now…");
      runApplication(pendingAnswers);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setUploadingProof(false);
    }
  };

  const startFlow = () => {
    pushUser("Yes, let's go");
    askNext(0, answers);
  };

  const handleButtonAnswer = (value, label) => {
    pushUser(label);
    const field = FIELDS[stepIdx];
    const updated = { ...answers, [field.key]: value };
    setAnswers(updated);
    askNext(stepIdx + 1, updated);
  };

  const handleTextSubmit = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    const field = FIELDS[stepIdx];

    if (field?.type === "number") {
      const digits = input.replace(/[^\d]/g, "");
      const num = Number(digits);
      if (!digits || (field.min !== undefined && num < field.min)) {
        pushUser(input);
        setInput("");
        setTimeout(() => pushBot(`That doesn't look right — please enter a number${field.min ? ` of at least ${field.min}` : ""}.`), 300);
        return;
      }
      pushUser(`₹${num.toLocaleString()}`);
      const updated = { ...answers, [field.key]: num };
      setAnswers(updated);
      setInput("");

      if (field.key === "salary" && bankIncome) {
        const ratio = Math.min(bankIncome, num) / Math.max(bankIncome, num);
        if (ratio < SALARY_MISMATCH_WARN_RATIO) {
          setTimeout(() => pushBot(
            `Just a heads up — that's noticeably different from your bank-verified income (₹${bankIncome.toLocaleString()}/mo). A large enough mismatch will cause your application to be rejected.`
          ), 300);
          setTimeout(() => askNext(stepIdx + 1, updated), 900);
          return;
        }
      }

      askNext(stepIdx + 1, updated);
      return;
    }

    // Free-text fallback before flow starts
    if (stepIdx === -1) {
      const yes = /yes|sure|ok|start|ready|go/i.test(input);
      setInput("");
      if (yes) { startFlow(); } else {
        pushUser(input);
        setTimeout(() => pushBot("No problem — whenever you're ready, just say \"yes\" to begin."), 300);
      }
    }
  };

  const runApplication = async (finalAnswers) => {
    setStepIdx(FIELDS.length);
    pushBot("Great, that's everything — running your application through the AI decision engine now…");
    setBusy(true);
    try {
      const { data } = await api.post("/loans/apply", {
        loan_amount: Number(finalAnswers.amount),
        employment_type: finalAnswers.emp,
        monthly_salary: Number(finalAnswers.salary),
        existing_emi: Number(finalAnswers.emi || 0),
        purpose: finalAnswers.purpose,
        tenure_months: Number(finalAnswers.tenure || 36),
      });
      setResult(data);
      const emiNote = typeof data.estimated_emi === "number"
        ? ` Estimated EMI: ₹${data.estimated_emi.toLocaleString()}/mo at ${(data.interest_rate * 100).toFixed(1)}% p.a.`
        : "";
      pushBot(`Decision ready: ${data.loan_status} · Eligibility score ${data.eligibility_score}/100.${emiNote} See the full breakdown below.`);
    } catch (e) {
      pushBot("Something went wrong running your application. You can try again or switch to the standard form.");
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const currentField = stepIdx >= 0 && stepIdx < FIELDS.length ? FIELDS[stepIdx] : null;
  const awaitingButtons = currentField?.type === "buttons";
  const awaitingText = stepIdx === -1 || currentField?.type === "number";

  return (
    <div className="user-portal min-h-screen flex flex-col">
      <header className="max-w-5xl mx-auto w-full flex items-center justify-between px-6 py-5">
        <Link to="/app" className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
            <ShieldCheck className="text-white" size={18} />
          </div>
          <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
        </Link>
        <Link to="/app/loan" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }}>Use the form instead →</Link>
      </header>

      <main className="max-w-2xl mx-auto w-full px-6 pb-10 flex-1 flex flex-col">
        <h1 className="font-serif text-3xl tracking-tight" style={{ color: "var(--sl-primary)" }}>Apply by chat</h1>

        <div ref={scrollRef} className="u-card mt-6 p-6 flex-1 overflow-y-auto" style={{ maxHeight: "50vh", minHeight: 320 }} data-testid="chat-window">
          {messages.map((m, i) => (
            <div key={i} className={`mb-3 flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
              <div className="px-4 py-2 rounded-2xl text-sm max-w-[80%]" style={{
                background: m.from === "user" ? "var(--sl-primary)" : "#EFF1E9",
                color: m.from === "user" ? "#FFF" : "var(--sl-text)",
              }}>
                {m.text}
              </div>
            </div>
          ))}
        </div>

        {result && (
          <div className="mt-6">
            <ResultCard result={result} onNew={() => nav(0)} onBack={() => nav("/app")} />
          </div>
        )}

        {!result && (
          <div className="mt-4">
            {stepIdx === -1 && (
              <button onClick={startFlow} className="btn-primary" data-testid="chat-start">Yes, let's go</button>
            )}

            {awaitingProof && (
              <label className="inline-flex items-center gap-2 text-sm px-4 py-2 rounded-lg border cursor-pointer"
                     style={{ borderColor: "var(--sl-border)", background: "#FFF", color: "var(--sl-primary)" }} data-testid="chat-income-proof-block">
                <Upload size={14} /> {uploadingProof ? "Uploading…" : "Upload salary slip (PDF/JPG/PNG)"}
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden" data-testid="chat-income-proof-input"
                       disabled={uploadingProof} onChange={(e) => uploadProofAndContinue(e.target.files?.[0])} />
              </label>
            )}

            {!awaitingProof && awaitingButtons && (
              <div className="flex gap-2 flex-wrap">
                {currentField.options.map((o) => (
                  <button key={o.value} onClick={() => handleButtonAnswer(o.value, o.label)}
                          className="px-4 py-2 rounded-full text-sm border"
                          style={{ borderColor: "var(--sl-border)", color: "var(--sl-primary)" }}
                          data-testid={`chat-opt-${o.value}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            )}

            {!awaitingProof && awaitingText && stepIdx !== -1 && (
              <form onSubmit={handleTextSubmit} className="flex gap-2">
                <input autoFocus value={input} onChange={(e) => setInput(e.target.value)}
                       className="flex-1 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]"
                       style={{ borderColor: "var(--sl-border)" }} placeholder="Type your answer…" data-testid="chat-input" />
                <button type="submit" className="btn-primary px-4" data-testid="chat-send"><Send size={16} /></button>
              </form>
            )}

            {busy && <div className="text-sm mt-2" style={{ color: "var(--sl-muted)" }}>Running AI decision…</div>}
          </div>
        )}
      </main>
    </div>
  );
}