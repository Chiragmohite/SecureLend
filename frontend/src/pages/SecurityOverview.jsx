import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Activity, Ban, Cpu, ShieldAlert } from "lucide-react";
import api from "@/lib/api";

export default function SecurityOverview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get("/security/overview");
        if (!cancelled) setData(data);
      } catch (e) {
        if (!cancelled) setError("Couldn't load live security data right now.");
      }
    };
    load();
    const interval = setInterval(load, 15000); // refresh every 15s for a "real-time" feel
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  return (
    <div className="user-portal min-h-screen">
      <header className="max-w-5xl mx-auto flex items-center justify-between px-6 py-5">
        <Link to="/" className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl flex items-center justify-center" style={{ background: "var(--sl-primary)" }}>
            <ShieldCheck className="text-white" size={18} />
          </div>
          <span className="font-serif text-2xl font-semibold" style={{ color: "var(--sl-primary)" }}>SecureLend</span>
        </Link>
        <Link to="/" className="text-sm underline-offset-4 hover:underline" style={{ color: "var(--sl-muted)" }}>← Back</Link>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3">
          <ShieldAlert size={24} style={{ color: "var(--sl-accent)" }}/>
          <h1 className="font-serif text-4xl tracking-tight" style={{ color: "var(--sl-primary)" }}>How your data is protected</h1>
        </div>
        <p className="mt-2 max-w-2xl" style={{ color: "var(--sl-muted)" }}>
          A live view into the security layer running under this platform. Counts refresh automatically.
          No IP addresses, emails, or individual request details are ever shown here — only aggregated,
          anonymized activity.
        </p>

        {error && <div className="mt-6 text-sm" style={{ color: "#B45309" }}>{error}</div>}

        {data && (
          <>
            <div className="grid sm:grid-cols-3 gap-4 mt-8">
              <StatCard icon={<Activity size={18} />} label="Detected, last hour" value={data.attacks_detected_last_hour} />
              <StatCard icon={<Activity size={18} />} label="Detected, last 24h" value={data.attacks_detected_last_24h} />
              <StatCard icon={<Ban size={18} />} label="IPs currently blocked" value={data.ips_currently_blocked} />
            </div>

            <div className="u-card p-6 mt-6">
              <div className="text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Detected by, last 24h</div>
              <div className="mt-3 flex gap-6">
                <div>
                  <div className="font-serif text-3xl" style={{ color: "var(--sl-primary)" }}>{data.detected_by_rule_engine}</div>
                  <div className="text-xs mt-1" style={{ color: "var(--sl-muted)" }}>Rule engine</div>
                </div>
                <div>
                  <div className="font-serif text-3xl" style={{ color: "var(--sl-primary)" }}>{data.detected_by_ml_model}</div>
                  <div className="text-xs mt-1" style={{ color: "var(--sl-muted)" }}>ML anomaly model</div>
                </div>
                <div className="flex items-center gap-2 ml-auto">
                  <Cpu size={16} style={{ color: data.ml_model_active ? "var(--sl-primary)" : "var(--sl-muted)" }} />
                  <span className="text-xs" style={{ color: "var(--sl-muted)" }}>
                    ML model {data.ml_model_active ? "active" : "not loaded"}
                  </span>
                </div>
              </div>
            </div>

            {data.attack_types_last_24h.length > 0 && (
              <div className="u-card p-6 mt-6">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Attack types, last 24h</div>
                <div className="mt-3 space-y-2">
                  {data.attack_types_last_24h.map((t) => (
                    <div key={t.type} className="flex items-center justify-between text-sm">
                      <span>{t.type}</span>
                      <span className="font-mono text-xs" style={{ color: "var(--sl-muted)" }}>{t.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="u-card p-6 mt-6">
              <div className="text-xs uppercase tracking-widest" style={{ color: "var(--sl-muted)" }}>Protections active</div>
              <ul className="mt-3 space-y-2 text-sm" style={{ color: "var(--sl-text)" }}>
                {data.protections_active.map((p) => (
                  <li key={p} className="flex items-start gap-2">
                    <ShieldCheck size={14} className="mt-0.5 shrink-0" style={{ color: "var(--sl-accent)" }} />
                    {p}
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-6 text-xs" style={{ color: "var(--sl-muted)" }}>
              Last updated: {new Date(data.generated_at).toLocaleTimeString()}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function StatCard({ icon, label, value }) {
  return (
    <div className="u-card p-5">
      <div className="flex items-center gap-2" style={{ color: "var(--sl-accent)" }}>{icon}</div>
      <div className="font-serif text-3xl mt-2" style={{ color: "var(--sl-primary)" }}>{value}</div>
      <div className="text-xs mt-1" style={{ color: "var(--sl-muted)" }}>{label}</div>
    </div>
  );
}