import { useState, useRef, useEffect } from "react";
import { MessageCircleQuestion, X, Send } from "lucide-react";
import api from "@/lib/api";

/**
 * BankAssistant.jsx
 * ------------------
 * Site-wide floating "ask the bank" widget. Currently rule-based FAQ
 * matching on the backend (backend/assistant.py) -- no LLM API key is
 * configured for this project. The backend module is written so a real
 * LLM (Grok/OpenAI) is a one-function swap later; nothing here needs to
 * change when that happens, since the request/response shape stays the same.
 */
export default function BankAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { from: "bot", text: "Hi, I'm the SecureLend assistant. Ask me about interest rates, tenure, eligibility, documents, or security." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (open) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open]);

  const send = async () => {
    const q = input.trim();
    if (!q || busy) return;
    setMessages((m) => [...m, { from: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const { data } = await api.post("/assistant/ask", { question: q });
      setMessages((m) => [...m, { from: "bot", text: data.answer }]);
    } catch (e) {
      setMessages((m) => [...m, { from: "bot", text: "Sorry, I couldn't process that just now." }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ position: "fixed", bottom: 20, right: 20, zIndex: 1000 }}>
      {open && (
        <div className="u-card p-0 overflow-hidden" style={{ width: 320, marginBottom: 12, boxShadow: "0 12px 32px rgba(0,0,0,0.18)" }} data-testid="bank-assistant-panel">
          <div className="px-4 py-3 flex items-center justify-between" style={{ background: "var(--sl-primary)" }}>
            <span className="text-sm font-semibold text-white">Ask the bank</span>
            <button onClick={() => setOpen(false)} aria-label="Close" data-testid="bank-assistant-close">
              <X size={16} className="text-white" />
            </button>
          </div>

          <div ref={scrollRef} className="px-4 py-3 space-y-3 overflow-y-auto" style={{ maxHeight: 320, background: "#FAFAF7" }}>
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
                <div className="max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed"
                     style={{
                       background: m.from === "user" ? "var(--sl-primary)" : "#EFF1E9",
                       color: m.from === "user" ? "#FFF" : "var(--sl-text)",
                     }}>
                  {m.text}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="px-3 py-2 rounded-xl text-xs" style={{ background: "#EFF1E9", color: "var(--sl-muted)" }}>…</div>
              </div>
            )}
          </div>

          <div className="border-t px-3 py-2 flex gap-2" style={{ borderColor: "var(--sl-border)" }}>
            <input
              data-testid="bank-assistant-input"
              value={input}
              disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); send(); } }}
              placeholder="Ask a question…"
              className="flex-1 px-3 py-2 rounded-lg border text-sm outline-none focus:border-[var(--sl-primary)]"
              style={{ borderColor: "var(--sl-border)" }}
            />
            <button onClick={send} disabled={busy || !input.trim()} data-testid="bank-assistant-send"
                    className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
              <Send size={14} className="text-white" />
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        data-testid="bank-assistant-toggle"
        className="w-14 h-14 rounded-full flex items-center justify-center"
        style={{ background: "var(--sl-primary)", boxShadow: "0 8px 20px rgba(0,0,0,0.25)" }}
        aria-label="Ask the bank"
      >
        {open ? <X size={22} className="text-white" /> : <MessageCircleQuestion size={22} className="text-white" />}
      </button>
    </div>
  );
}