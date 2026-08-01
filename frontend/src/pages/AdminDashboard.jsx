import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Shield, Activity, Ban, Users, CreditCard, LogOut, RefreshCw,
  AlertTriangle, Zap, Terminal, TrendingUp, ChevronRight, ShieldAlert
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  BarChart, Bar, Cell
} from "recharts";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const SEV_COLOR = {
  critical: "var(--soc-critical)",
  high: "#FF6B4A",
  medium: "var(--soc-warning)",
  low: "var(--soc-info)",
};

function MetaStat({ label, value, testid }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>{label}</div>
      <div className="text-sm" style={{ color: "var(--soc-text)" }} data-testid={testid}>{value}</div>
    </div>
  );
}

function SourceBadge({ source }) {
  const isML = source === "ml";
  return (
    <span
      className="inline-block font-mono uppercase tracking-widest"
      style={{
        fontSize: "0.6rem",
        padding: "2px 6px",
        borderRadius: 2,
        border: `1px solid ${isML ? "var(--soc-info)" : "var(--soc-warning)"}`,
        color: isML ? "var(--soc-info)" : "var(--soc-warning)",
        background: isML ? "rgba(10,132,255,0.08)" : "rgba(255,159,10,0.08)",
      }}
      data-testid={`src-badge-${isML ? "ml" : "rule"}`}
    >
      {isML ? "ML" : "RULE"}
    </span>
  );
}

const TABS = [
  { key: "overview", label: "OVERVIEW", icon: Activity },
  { key: "attacks",  label: "ATTACK FEED", icon: ShieldAlert },
  { key: "blocked",  label: "BLOCKED IPS", icon: Ban },
  { key: "users",    label: "USERS", icon: Users },
  { key: "loans",    label: "LOANS", icon: CreditCard },
  { key: "demo",     label: "SECURITY DEMO", icon: Zap },
];

export default function AdminDashboard() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState(null);
  const [attacks, setAttacks] = useState([]);
  const [blocked, setBlocked] = useState([]);
  const [users, setUsers] = useState([]);
  const [loans, setLoans] = useState([]);

  const load = useCallback(async () => {
    try {
      const [s, a, b, u, l] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/attacks?limit=100"),
        api.get("/admin/blocked-ips"),
        api.get("/admin/users"),
        api.get("/admin/loans"),
      ]);
      setStats(s.data); setAttacks(a.data); setBlocked(b.data); setUsers(u.data); setLoans(l.data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  }, []);

  useEffect(() => { load(); const iv = setInterval(load, 8000); return () => clearInterval(iv); }, [load]);

  const doLogout = async () => { await logout(); nav("/", { replace: true }); };

  return (
    <div className="soc-shell">
      {/* Header */}
      <header className="border-b" style={{ borderColor: "var(--soc-border)", background: "rgba(5,8,20,0.8)", backdropFilter: "blur(8px)" }}>
        <div className="max-w-[1600px] mx-auto flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded flex items-center justify-center" style={{ background: "var(--soc-critical)" }}>
              <Shield className="text-white" size={18}/>
            </div>
            <div>
              <div className="font-mono text-sm uppercase tracking-widest" style={{ color: "var(--soc-text)" }}>SecureLend · SOC</div>
              <div className="font-mono text-xs" style={{ color: "var(--soc-muted)" }}>Command Center · Live</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={load} className="text-xs font-mono uppercase tracking-widest inline-flex items-center gap-2 px-3 py-2 rounded" style={{ background: "var(--soc-surface)", color: "var(--soc-text)", border: "1px solid var(--soc-border)" }} data-testid="ad-refresh">
              <RefreshCw size={12}/> Refresh
            </button>
            <span className="font-mono text-xs" style={{ color: "var(--soc-muted)" }}>{user?.email}</span>
            <button onClick={doLogout} className="text-xs font-mono uppercase tracking-widest inline-flex items-center gap-2 px-3 py-2 rounded" style={{ background: "var(--soc-critical)", color: "#FFF" }} data-testid="ad-logout">
              <LogOut size={12}/> Sign out
            </button>
          </div>
        </div>
        {/* Tabs */}
        <div className="max-w-[1600px] mx-auto px-6 flex flex-wrap gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                data-testid={`ad-tab-${t.key}`}
                className="inline-flex items-center gap-2 px-4 py-3 text-xs font-mono uppercase tracking-widest"
                style={{
                  color: active ? "var(--soc-text)" : "var(--soc-muted)",
                  borderBottom: `2px solid ${active ? "var(--soc-critical)" : "transparent"}`,
                }}
              >
                <Icon size={12}/> {t.label}
              </button>
            );
          })}
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6">
        {tab === "overview" && <Overview stats={stats} attacks={attacks}/>}
        {tab === "attacks" && <AttackFeed attacks={attacks}/>}
        {tab === "blocked" && <BlockedIPs blocked={blocked} reload={load}/>}
        {tab === "users" && <UsersTable users={users}/>}
        {tab === "loans" && <LoansTable loans={loans} reload={load}/>}
        {tab === "demo" && <SecurityDemo reload={load}/>}
      </main>
    </div>
  );
}

/* ---------- OVERVIEW ---------- */
function Overview({ stats, attacks }) {
  if (!stats) return <div className="font-mono text-sm" style={{ color: "var(--soc-muted)" }}>Loading telemetry…</div>;
  const cards = [
    { k: "Attacks (24h)", v: stats.today_attacks, sub: `${stats.total_attacks} total`, tint: "var(--soc-critical)" },
    { k: "Blocked IPs", v: stats.blocked_ips, sub: "Active blocks", tint: "var(--soc-warning)" },
    { k: "Users", v: stats.total_users, sub: "Onboarded", tint: "var(--soc-info)" },
    { k: "Loans", v: stats.total_loans, sub: `${stats.approved_loans} approved`, tint: "var(--soc-success)" },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {cards.map((c) => (
        <div key={c.k} className="s-card p-5" data-testid={`ad-stat-${c.k.replace(/\s+/g,'-').toLowerCase()}`}>
          <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>{c.k}</div>
          <div className="font-mono text-4xl mt-2" style={{ color: c.tint }}>{c.v}</div>
          <div className="font-mono text-xs mt-1" style={{ color: "var(--soc-muted)" }}>{c.sub}</div>
        </div>
      ))}

      <div className="s-card p-5 md:col-span-3">
        <div className="flex items-center justify-between">
          <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>Attacks · Last 7 days</div>
          <TrendingUp size={14} style={{ color: "var(--soc-info)" }}/>
        </div>
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stats.timeline}>
              <CartesianGrid stroke="#1E293B" strokeDasharray="3 3"/>
              <XAxis dataKey="date" stroke="#94A3B8" fontSize={11} tickFormatter={(v)=>v.slice(5)}/>
              <YAxis stroke="#94A3B8" fontSize={11} allowDecimals={false}/>
              <Tooltip contentStyle={{ background: "#0D111D", border: "1px solid #1E293B", fontFamily: "JetBrains Mono" }}/>
              <Line type="monotone" dataKey="count" stroke="#FF453A" strokeWidth={2} dot={{ r: 3, fill: "#FF453A" }}/>
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="s-card p-5">
        <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>Attack Type Distribution</div>
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stats.by_type} layout="vertical" margin={{ left: 10, right: 10 }}>
              <XAxis type="number" stroke="#94A3B8" fontSize={10} allowDecimals={false}/>
              <YAxis dataKey="type" type="category" stroke="#94A3B8" fontSize={10} width={140}/>
              <Tooltip contentStyle={{ background: "#0D111D", border: "1px solid #1E293B", fontFamily: "JetBrains Mono" }}/>
              <Bar dataKey="count" radius={[0, 2, 2, 0]}>
                {stats.by_type.map((_, i) => <Cell key={i} fill={["#FF453A","#FF9F0A","#0A84FF","#30D158","#B85CFF","#FF6B4A","#FFCC00","#94A3B8"][i % 8]}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Live feed */}
      <div className="s-card live p-5 md:col-span-4 scanlines" data-testid="ad-live-feed">
        <div className="flex items-center justify-between">
          <div className="font-mono text-xs uppercase tracking-widest blink-dot" style={{ color: "var(--soc-critical)" }}>LIVE ATTACK FEED</div>
          <div className="font-mono text-xs" style={{ color: "var(--soc-muted)" }}>Streaming · polling 8s</div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="soc-table w-full">
            <thead>
              <tr>
                <th>Time</th><th>Type</th><th>Source</th><th>Severity</th><th>IP</th><th>Endpoint</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {attacks.slice(0, 12).map((a) => (
                <tr key={a.id}>
                  <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{new Date(a.timestamp).toLocaleTimeString()}</td>
                  <td>{a.attack_type}</td>
                  <td><SourceBadge source={a.source}/></td>
                  <td className="font-mono uppercase" style={{ color: SEV_COLOR[a.severity] || "var(--soc-muted)" }}>{a.severity}</td>
                  <td className="font-mono" style={{ color: "var(--soc-text)" }}>{a.ip_address}</td>
                  <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{a.endpoint}</td>
                  <td className="font-mono uppercase" style={{ color: a.status === "blocked" ? "var(--soc-critical)" : "var(--soc-warning)" }}>{a.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ---------- ATTACK FEED ---------- */
function AttackFeed({ attacks }) {
  return (
    <div className="s-card scanlines" data-testid="ad-attacks-panel">
      <div className="px-5 py-4 border-b" style={{ borderColor: "var(--soc-border)" }}>
        <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>Attack Log · Most recent 100</div>
      </div>
      <div className="overflow-x-auto">
        <table className="soc-table w-full">
          <thead>
            <tr>
              <th>Timestamp</th><th>Type</th><th>Source</th><th>Severity</th><th>IP</th><th>Endpoint</th><th>Details</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {attacks.map((a) => (
              <tr key={a.id}>
                <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{new Date(a.timestamp).toLocaleString()}</td>
                <td>{a.attack_type}</td>
                <td><SourceBadge source={a.source}/></td>
                <td className="font-mono uppercase" style={{ color: SEV_COLOR[a.severity] || "var(--soc-muted)" }}>{a.severity}</td>
                <td className="font-mono">{a.ip_address}</td>
                <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{a.endpoint}</td>
                <td className="font-mono text-xs" style={{ color: "var(--soc-muted)" }}>{a.details}</td>
                <td className="font-mono uppercase" style={{ color: a.status === "blocked" ? "var(--soc-critical)" : "var(--soc-warning)" }}>{a.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- BLOCKED IPS ---------- */
function BlockedIPs({ blocked, reload }) {
  const unblock = async (ip) => {
    try { await api.post(`/admin/blocked-ips/${ip}/unblock`); toast.success(`${ip} unblocked`); reload(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  return (
    <div className="s-card" data-testid="ad-blocked-panel">
      <div className="px-5 py-4 border-b" style={{ borderColor: "var(--soc-border)" }}>
        <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>Blocked IPs · {blocked.length} active</div>
      </div>
      <table className="soc-table w-full">
        <thead>
          <tr><th>IP</th><th>Reason</th><th>Blocked at</th><th></th></tr>
        </thead>
        <tbody>
          {blocked.length === 0 && (
            <tr><td colSpan={4} className="text-center py-8 font-mono" style={{ color: "var(--soc-muted)" }}>No active blocks</td></tr>
          )}
          {blocked.map((b) => (
            <tr key={b.id}>
              <td className="font-mono" style={{ color: "var(--soc-text)" }}>{b.ip_address}</td>
              <td>{b.reason}</td>
              <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{new Date(b.blocked_at).toLocaleString()}</td>
              <td>
                <button onClick={() => unblock(b.ip_address)} className="text-xs font-mono uppercase tracking-widest px-3 py-1 rounded" style={{ background: "var(--soc-info)", color: "#FFF" }} data-testid={`ad-unblock-${b.ip_address}`}>Unblock</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- USERS ---------- */
function UsersTable({ users }) {
  return (
    <div className="s-card" data-testid="ad-users-panel">
      <div className="px-5 py-4 border-b" style={{ borderColor: "var(--soc-border)" }}>
        <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>Users · {users.length}</div>
      </div>
      <table className="soc-table w-full">
        <thead>
          <tr><th>Name</th><th>Email</th><th>Phone</th><th>PAN</th><th>Joined</th></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.full_name}</td>
              <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{u.email}</td>
              <td className="font-mono">+91-{u.phone}</td>
              <td className="font-mono">{u.pan}</td>
              <td className="font-mono" style={{ color: "var(--soc-muted)" }}>{new Date(u.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- LOANS ---------- */
function LoansTable({ loans, reload }) {
  const override = async (id, status) => {
    try { await api.post(`/admin/loans/${id}/override`, { status }); toast.success(`Loan set to ${status}`); reload(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  return (
    <div className="s-card" data-testid="ad-loans-panel">
      <div className="px-5 py-4 border-b" style={{ borderColor: "var(--soc-border)" }}>
        <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-muted)" }}>Loans · {loans.length}</div>
      </div>
      <table className="soc-table w-full">
        <thead>
          <tr><th>User</th><th>Amount</th><th>Purpose</th><th>Score</th><th>Risk</th><th>Status</th><th>Override</th></tr>
        </thead>
        <tbody>
          {loans.map((l) => (
            <tr key={l.id}>
              <td>{l.user_name}</td>
              <td className="font-mono">₹{l.loan_amount.toLocaleString()}</td>
              <td>{l.purpose}</td>
              <td className="font-mono">{l.eligibility_score}</td>
              <td className="font-mono" style={{ color: l.risk_level === "LOW" ? "var(--soc-success)" : l.risk_level === "MEDIUM" ? "var(--soc-warning)" : "var(--soc-critical)" }}>{l.risk_level}</td>
              <td className="font-mono" style={{ color: l.loan_status === "Approved" ? "var(--soc-success)" : l.loan_status === "Rejected" ? "var(--soc-critical)" : "var(--soc-warning)" }}>{l.loan_status}</td>
              <td>
                <div className="flex gap-1">
                  <button onClick={() => override(l.id, "Approved")} className="text-[10px] font-mono uppercase px-2 py-1 rounded" style={{ background: "rgba(48,209,88,0.15)", color: "var(--soc-success)" }} data-testid={`ad-approve-${l.id}`}>Approve</button>
                  <button onClick={() => override(l.id, "Rejected")} className="text-[10px] font-mono uppercase px-2 py-1 rounded" style={{ background: "rgba(255,69,58,0.15)", color: "var(--soc-critical)" }} data-testid={`ad-reject-${l.id}`}>Reject</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- SECURITY DEMO ---------- */
const DEMO = [
  { kind: "sql_injection", title: "SQL Injection", desc: "Simulates ' OR '1'='1' -- payload hitting /api/auth/login. Rule engine intercepts.", icon: Terminal },
  { kind: "brute_force", title: "Brute Force Login", desc: "5+ rapid failures from same IP → automatic IP block & attack log.", icon: AlertTriangle },
  { kind: "bot_flood", title: "Bot Flood", desc: "150+ requests/minute triggers hard block via rate limiter.", icon: Zap },
  { kind: "unauthorized_admin", title: "Unauthorized Admin", desc: "Non-admin JWT attempts to hit /admin route → 403 + logged.", icon: Shield },
  { kind: "malicious_upload", title: "Malicious File Upload", desc: "kyc_document.exe is blocked at the upload validator.", icon: ShieldAlert },
  { kind: "xss", title: "XSS Attempt", desc: "<script> payload detected & sanitised before reaching handler.", icon: Terminal },
];

function SecurityDemo({ reload }) {
  const [busy, setBusy] = useState(null);
  const [lastVerdicts, setLastVerdicts] = useState({});
  const [modelHealth, setModelHealth] = useState(null);

  useEffect(() => {
    api.get("/admin/ml/health").then((r) => setModelHealth(r.data)).catch(() => {});
  }, []);

  const trigger = async (kind) => {
    setBusy(kind);
    try {
      const { data } = await api.post("/admin/demo/attack", { kind });
      setLastVerdicts((prev) => ({ ...prev, [kind]: data }));
      const mlLabel = data.ml_verdict?.predicted_type ?? "n/a";
      toast.success(`Fired ${data.rule_log.attack_type} · IP ${data.simulated_ip} · ML=${mlLabel}`);
      reload();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally { setBusy(null); }
  };

  return (
    <div>
      {/* Model metadata card */}
      {modelHealth && (
        <div className="s-card p-5 mb-4" data-testid="ad-ml-health">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-info)" }}>
                Trained IDS Model · {modelHealth.model_loaded ? "loaded" : "unavailable"}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: "var(--soc-muted)" }}>
                RandomForest + IsolationForest · trained on {modelHealth.training_rows?.toLocaleString()} rows · tested on {modelHealth.test_rows?.toLocaleString()}
              </div>
            </div>
            <div className="flex gap-6 flex-wrap font-mono text-xs">
              <MetaStat label="ANOMALY THR" value={modelHealth.anomaly_threshold?.toFixed?.(6)} testid="ad-ml-thr"/>
              <MetaStat label="RECALL @ THR" value={`${(modelHealth.attack_recall_at_threshold * 100).toFixed(2)}%`}/>
              <MetaStat label="FPR @ THR" value={`${(modelHealth.false_positive_rate_at_threshold * 100).toFixed(2)}%`}/>
              <MetaStat label="CLASSES" value={modelHealth.classes_in_order?.length}/>
              <MetaStat label="FEATURES" value={modelHealth.features_in_order?.length}/>
            </div>
          </div>
          <div className="mt-3 flex gap-2 flex-wrap">
            {modelHealth.classes_in_order?.map((c) => (
              <span key={c} className="font-mono text-[10px] uppercase" style={{ padding: "2px 6px", border: "1px solid var(--soc-border)", color: c === "normal" ? "var(--soc-success)" : "var(--soc-warning)" }}>{c}</span>
            ))}
          </div>
        </div>
      )}

      <div className="s-card p-5 mb-4">
        <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--soc-warning)" }}>⚠ Demo Panel · Fires both layers (rule engine + trained ML model)</div>
        <p className="mt-2 font-mono text-sm" style={{ color: "var(--soc-muted)" }}>
          Each trigger creates a RULE log entry AND routes the same synthetic event through the trained Random-Forest + IsolationForest scorer. You'll see the ML verdict inline (predicted class, confidence, anomaly score) plus a matching ML log in the Attack Feed.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {DEMO.map((d) => {
          const Icon = d.icon;
          const last = lastVerdicts[d.kind];
          const ml = last?.ml_verdict;
          return (
            <div key={d.kind} className="s-card p-5 flex flex-col" data-testid={`ad-demo-${d.kind}`}>
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded flex items-center justify-center" style={{ background: "rgba(255,69,58,0.1)" }}>
                  <Icon size={18} style={{ color: "var(--soc-critical)" }}/>
                </div>
                <div className="font-mono text-sm uppercase tracking-widest" style={{ color: "var(--soc-text)" }}>{d.title}</div>
              </div>
              <p className="mt-3 text-xs font-mono" style={{ color: "var(--soc-muted)" }}>{d.desc}</p>

              {last && (
                <div className="mt-4 space-y-2 text-xs font-mono" data-testid={`ad-demo-verdicts-${d.kind}`}>
                  <div className="flex items-center gap-2">
                    <SourceBadge source="rule"/>
                    <span style={{ color: "var(--soc-critical)" }}>BLOCKED</span>
                    <span style={{ color: "var(--soc-muted)" }}>{last.rule_log?.attack_type}</span>
                  </div>
                  {ml ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <SourceBadge source="ml"/>
                      <span
                        style={{ color: ml.action === "block" ? "var(--soc-critical)" : ml.action === "flag" ? "var(--soc-warning)" : "var(--soc-success)" }}
                        data-testid={`ad-demo-ml-action-${d.kind}`}
                      >
                        {ml.action.toUpperCase()}
                      </span>
                      <span style={{ color: "var(--soc-text)" }} data-testid={`ad-demo-ml-predicted-${d.kind}`}>{ml.predicted_type}</span>
                      <span style={{ color: "var(--soc-muted)" }}>
                        conf=<span style={{ color: "var(--soc-info)" }} data-testid={`ad-demo-ml-conf-${d.kind}`}>{ml.confidence.toFixed(3)}</span>
                        {" · "}anom=<span style={{ color: ml.is_anomalous ? "var(--soc-critical)" : "var(--soc-muted)" }} data-testid={`ad-demo-ml-anom-${d.kind}`}>{ml.anomaly_score.toFixed(3)}</span>
                        {" · "}thr={ml.anomaly_threshold.toFixed(3)}
                      </span>
                    </div>
                  ) : (
                    <div style={{ color: "var(--soc-muted)" }}>ML scorer unavailable</div>
                  )}
                  <div style={{ color: "var(--soc-muted)" }}>src IP <span className="font-mono" style={{ color: "var(--soc-text)" }}>{last.simulated_ip}</span></div>
                </div>
              )}

              <div className="flex-1"/>
              <button
                onClick={() => trigger(d.kind)}
                disabled={busy === d.kind}
                className="mt-5 w-full text-xs font-mono uppercase tracking-widest py-2 rounded inline-flex items-center justify-center gap-2"
                style={{ background: "var(--soc-critical)", color: "#FFF" }}
                data-testid={`ad-demo-trigger-${d.kind}`}
              >
                {busy === d.kind ? "Firing…" : <>Trigger attack <ChevronRight size={14}/></>}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
