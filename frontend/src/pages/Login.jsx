import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Check, LogIn } from "lucide-react";
import { errorMessage } from "../api.js";
import { ROLE_LABELS, useAuth } from "../auth.jsx";
import { ErrorBox } from "../components/ui.jsx";
import LoginBackground from "../components/LoginBackground.jsx";

// Seed-script demo accounts (password Demo@12345). Remove this block for a real deployment.
const DEMO = [
  { label: "Super Administrator", email: "superadmin@skillwatch.local" },
  { label: "Monitoring Officer", email: "officer@skillwatch.local" },
  { label: "Centre Administrator (Pune)", email: "admin.sc001@skillwatch.local" },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("idle"); // "idle" | "success" (welcome animation playing)
  const [who, setWho] = useState(null);
  const hold = useRef(false); // keeps this page on screen while the welcome animation plays

  // After the welcome animation, open the dashboard (almost at once if the person prefers reduced motion).
  useEffect(() => {
    if (phase !== "success") return undefined;
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setTimeout(() => navigate(location.state?.from || "/overview", { replace: true }), reduce ? 150 : 1700);
    return () => clearTimeout(timer);
  }, [phase]); // eslint-disable-line react-hooks/exhaustive-deps

  if (user && !hold.current) return <Navigate to="/overview" replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    hold.current = true;
    try {
      const signedIn = await login(email.trim(), password);
      setWho(signedIn);
      setPhase("success");
    } catch (err) {
      hold.current = false;
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <LoginBackground />
      <div className="relative z-10 w-full max-w-sm">
        <div className={`glass rise space-y-4 p-6 transition duration-500 ease-out ${phase === "success" ? "scale-95 opacity-0" : ""}`} style={{ "--i": 1 }}>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight text-white">SkillWatch AI</h1>
            <p className="text-sm text-slate-400">Sign in to the compliance dashboard</p>
          </div>
          {error && <ErrorBox message={error} />}
          <form onSubmit={submit} className="space-y-3">
            <label className="block text-sm text-slate-300">
              Email
              <input className="input mt-1" type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="block text-sm text-slate-300">
              Password
              <input className="input mt-1" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button className="btn-primary w-full justify-center" disabled={busy}>
              {phase === "success" ? <Check className="h-4 w-4" /> : <LogIn className="h-4 w-4" />}{" "}
              {phase === "success" ? "Signed in" : busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <div className="border-t border-white/10 pt-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">Demo accounts (password Demo@12345)</div>
            <div className="flex flex-col gap-1.5">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-left text-sm text-slate-200 transition hover:-translate-y-0.5 hover:border-cobalt-400/60 hover:bg-cobalt/20 active:scale-95"
                  onClick={() => {
                    setEmail(d.email);
                    setPassword("Demo@12345");
                  }}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      {phase === "success" && (
        <div className="signin-overlay" role="status" aria-live="polite">
          <div className="signin-ring" aria-hidden="true" />
          <div className="signin-content">
            <svg className="signin-check" viewBox="0 0 52 52" aria-hidden="true">
              <circle cx="26" cy="26" r="24" />
              <path d="M15 27l8 8 15-17" />
            </svg>
            <div className="text-2xl font-bold tracking-tight text-white">Welcome back</div>
            {who && <div className="mt-1 text-sm text-slate-200">{who.full_name} · {ROLE_LABELS[who.role]}</div>}
            <div className="mt-2 text-xs uppercase tracking-widest text-acid">Opening your dashboard…</div>
          </div>
        </div>
      )}
    </div>
  );
}