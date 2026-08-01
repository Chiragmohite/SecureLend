import { Link } from "react-router-dom";
import { ShieldCheck, Sparkles, Activity, LockKeyhole, ArrowUpRight, CircleDollarSign } from "lucide-react";

export default function Landing() {
  return (
    <div className="user-portal">
      {/* Nav */}
      <header className="w-full sticky top-0 z-30 backdrop-blur-xl" style={{ background: "rgba(249,249,246,0.72)", borderBottom: "1px solid var(--sl-border)" }}>
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-4">
          <Link to="/" className="flex items-center gap-2" data-testid="brand-logo">
            <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
              <ShieldCheck className="text-white" size={18} />
            </div>
            <span className="font-serif text-2xl font-semibold tracking-tight" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
          </Link>
          <nav className="hidden md:flex items-center gap-8 font-medium text-sm" style={{ color: "var(--sl-muted)" }}>
            <a href="#how" className="hover:text-[var(--sl-primary)]">How it works</a>
            <a href="#security" className="hover:text-[var(--sl-primary)]">Security</a>
            <a href="#ai" className="hover:text-[var(--sl-primary)]">AI Decisioning</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link to="/login" className="btn-outline-user" data-testid="nav-login">Sign in</Link>
            <Link to="/register" className="btn-primary" data-testid="nav-signup">Apply now</Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-7xl mx-auto px-6 pt-16 pb-24">
        <div className="grid md:grid-cols-12 gap-12 items-center">
          <div className="md:col-span-7">
            <span className="chip" style={{ background: "#EAF1EC", color: "var(--sl-primary)" }} data-testid="hero-badge">
              <Sparkles size={12} /> Agentic AI Underwriting · Live IDS Protection
            </span>
            <h1 className="mt-6 font-serif tracking-tight" style={{ color: "var(--sl-primary)", fontSize: "clamp(2.5rem, 5vw, 4.25rem)", lineHeight: 1.05, fontWeight: 700 }}>
              A loan platform that
              <br />
              <span style={{ color: "var(--sl-accent)" }} className="italic">actually watches</span> its own back.
            </h1>
            <p className="mt-6 text-lg max-w-xl" style={{ color: "var(--sl-muted)" }}>
              SecureLend fuses transparent AI credit scoring with a real-time hybrid Intrusion Detection System — every request is inspected, every anomaly logged, every decision explainable.
            </p>
            <div className="mt-9 flex flex-wrap gap-4">
              <Link to="/register" className="btn-primary inline-flex items-center gap-2" data-testid="hero-cta-apply">
                Start your application <ArrowUpRight size={18} />
              </Link>
              <Link to="/login" className="btn-outline-user inline-flex items-center gap-2" data-testid="hero-cta-signin">
                <LockKeyhole size={16} /> Existing customer
              </Link>
            </div>
            <div className="mt-10 grid grid-cols-3 gap-6 max-w-lg">
              {[
                { k: "0.9s", v: "AI decision" },
                { k: "8+", v: "IDS rules" },
                { k: "ML", v: "Anomaly engine" },
              ].map((s) => (
                <div key={s.k}>
                  <div className="font-serif text-3xl font-semibold" style={{ color: "var(--sl-primary)" }}>{s.k}</div>
                  <div className="text-xs uppercase tracking-widest mt-1" style={{ color: "var(--sl-muted)" }}>{s.v}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="md:col-span-5">
            <div className="u-card p-2 relative overflow-hidden">
              <img
                src="https://images.unsplash.com/photo-1467007849282-42dad96c2312?auto=format&fit=crop&w=1000&q=80"
                alt="Mobile onboarding"
                className="rounded-xl w-full h-[520px] object-cover"
              />
              <div className="absolute left-8 bottom-8 right-8 backdrop-blur-xl rounded-2xl p-5" style={{ background: "rgba(255,255,255,0.86)", border: "1px solid var(--sl-border)" }}>
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
                    <CircleDollarSign className="text-white" size={18} />
                  </div>
                  <div className="flex-1">
                    <div className="font-semibold text-sm">Eligibility score</div>
                    <div className="text-xs" style={{ color: "var(--sl-muted)" }}>Weighted • explainable • auditable</div>
                  </div>
                  <div className="font-serif text-3xl font-semibold" style={{ color: "var(--sl-accent)" }}>78</div>
                </div>
                <div className="mt-3 h-2 rounded-full" style={{ background: "#E9EBE3" }}>
                  <div className="h-2 rounded-full" style={{ width: "78%", background: "var(--sl-primary)" }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="max-w-7xl mx-auto px-6 py-16" style={{ borderTop: "1px solid var(--sl-border)" }}>
        <h2 className="font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>Four steps. No dark patterns.</h2>
        <p className="text-base mt-3 max-w-2xl" style={{ color: "var(--sl-muted)" }}>
          Verify who you are, connect your bank with explicit consent, tell us what you need, and get a transparent decision — factor by factor.
        </p>
        <div className="mt-10 grid md:grid-cols-4 gap-6">
          {[
            { n: "01", t: "Verify mobile & PAN", d: "OTP-based phone check plus regex-validated PAN lookup." },
            { n: "02", t: "Link bank (with consent)", d: "Explicit consent screen. We only read what we need to underwrite." },
            { n: "03", t: "Apply for loan", d: "Amount, tenure, purpose. That’s it. No paperwork loops." },
            { n: "04", t: "See the reasoning", d: "Every factor & weight shown. Approved, review, or rejected — you know why." },
          ].map((s) => (
            <div key={s.n} className="u-card p-6" data-testid={`step-card-${s.n}`}>
              <div className="font-mono text-xs" style={{ color: "var(--sl-accent)" }}>{s.n}</div>
              <div className="font-serif text-xl mt-3" style={{ color: "var(--sl-primary)" }}>{s.t}</div>
              <div className="text-sm mt-2" style={{ color: "var(--sl-muted)" }}>{s.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Security */}
      <section id="security" className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <span className="chip" style={{ background: "#F5E7E1", color: "var(--sl-accent)" }}>Hybrid IDS</span>
            <h2 className="mt-4 font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>Rules that block. ML that notices.</h2>
            <p className="mt-4" style={{ color: "var(--sl-muted)" }}>
              A rule engine handles known signatures — SQL injection, brute force, unauthorised admin, malicious uploads. An Isolation Forest watches request-rate baselines to spot the things rules can’t name yet.
            </p>
            <ul className="mt-6 space-y-3 text-sm" style={{ color: "var(--sl-text)" }}>
              {["SQL injection & XSS payload scanning on every request", "Brute-force lockout after 5 failed attempts", "Bot flood detection with per-IP rate windows", "Role-guarded admin endpoints", "File upload whitelist (.pdf/.jpg/.png) + size cap", "IsolationForest baseline for anomalous traffic"].map((t) => (
                <li key={t} className="flex items-start gap-3">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full inline-block" style={{ background: "var(--sl-accent)" }} />
                  {t}
                </li>
              ))}
            </ul>
          </div>
          <div className="u-card p-8" style={{ background: "var(--soc-bg)", color: "var(--soc-text)" }}>
            <div className="flex items-center gap-2 font-mono text-xs" style={{ color: "var(--soc-warning)" }}>
              <Activity size={14} /> LIVE ATTACK FEED · sample
            </div>
            <div className="mt-4 space-y-2 font-mono text-xs">
              {[
                ["12:04:33", "SQL Injection", "185.220.101.4", "blocked"],
                ["12:04:12", "Brute Force Login", "94.23.11.72", "blocked"],
                ["12:03:58", "Anomalous Traffic", "203.99.47.2", "flagged"],
                ["12:03:41", "Malicious File Upload", "45.155.204.8", "blocked"],
                ["12:03:20", "Bot Flood", "77.88.55.19", "blocked"],
              ].map((r, i) => (
                <div key={i} className="grid grid-cols-4 gap-3 py-1" style={{ borderBottom: "1px solid var(--soc-border)" }}>
                  <span style={{ color: "var(--soc-muted)" }}>{r[0]}</span>
                  <span style={{ color: r[3] === "blocked" ? "var(--soc-critical)" : "var(--soc-warning)" }}>{r[1]}</span>
                  <span>{r[2]}</span>
                  <span className="uppercase" style={{ color: r[3] === "blocked" ? "var(--soc-critical)" : "var(--soc-warning)" }}>{r[3]}</span>
                </div>
              ))}
            </div>
            <div className="mt-6 flex items-center justify-between">
              <div className="font-mono text-xs" style={{ color: "var(--soc-muted)" }}>Admin SOC console</div>
              <Link to="/login" className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--soc-info)" }} data-testid="admin-cta">Open →</Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-20 py-10" style={{ borderTop: "1px solid var(--sl-border)", background: "#F1F3EC" }}>
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
              <ShieldCheck className="text-white" size={14} />
            </div>
            <span className="font-serif text-lg" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
          </div>
          <div className="text-xs" style={{ color: "var(--sl-muted)" }}>
            Demonstration project · Fintech + Agentic AI + Cybersecurity · Data & bank flows are simulated
          </div>
        </div>
      </footer>
    </div>
  );
}
