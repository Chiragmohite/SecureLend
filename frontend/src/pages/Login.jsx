import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck, LogIn } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(email, password);
      toast.success(`Welcome back, ${u.full_name.split(" ")[0]}`);
      nav(u.role === "admin" ? "/admin" : (loc.state?.from || "/app"), { replace: true });
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="user-portal min-h-screen flex flex-col">
      <header className="max-w-7xl w-full mx-auto flex items-center justify-between px-6 py-5">
        <Link to="/" className="flex items-center gap-2" data-testid="login-brand">
          <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
            <ShieldCheck className="text-white" size={18} />
          </div>
          <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
        </Link>
        <Link to="/register" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }} data-testid="link-register">
          Don’t have an account? Register
        </Link>
      </header>

      <main className="flex-1 grid md:grid-cols-2">
        <div className="hidden md:block" style={{ background: "linear-gradient(135deg, #1A3626 0%, #24462F 100%)" }}>
          <div className="h-full flex flex-col justify-end p-14 text-white">
            <div className="max-w-md">
              <div className="chip mb-6" style={{ background: "rgba(255,255,255,0.12)", color: "#FFF" }}>Trusted by simulated demo customers</div>
              <div className="font-serif text-4xl leading-tight">
                Your credit story, seen clearly — and defended in real time.
              </div>
              <p className="mt-4 text-white/70">
                Every login attempt is inspected by our hybrid intrusion detection system. Five failed tries and the IP gets blocked. That’s the deal.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-center p-8">
          <form onSubmit={submit} className="u-card p-10 w-full max-w-md" data-testid="login-form">
            <h1 className="font-serif text-3xl" style={{ color: "var(--sl-primary)" }}>Sign in</h1>
            <p className="mt-2 text-sm" style={{ color: "var(--sl-muted)" }}>Access your applications and decision history.</p>

            <label className="block mt-8 text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Email</label>
            <input data-testid="login-email" required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full mt-2 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)", background: "#FFF" }} />

            <label className="block mt-5 text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Password</label>
            <input data-testid="login-password" required type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full mt-2 px-4 py-3 rounded-lg border outline-none focus:border-[var(--sl-primary)]" style={{ borderColor: "var(--sl-border)", background: "#FFF" }} />

            <button data-testid="login-submit" disabled={busy} type="submit" className="btn-primary mt-8 w-full inline-flex items-center justify-center gap-2">
              <LogIn size={16} /> {busy ? "Signing in…" : "Sign in"}
            </button>

            <div className="mt-6 text-xs" style={{ color: "var(--sl-muted)" }}>
              Admin? Use your admin credentials above; you’ll be routed to the SOC console.
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}
