import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { errorMessage } from "../api.js";
import { useAuth } from "../auth.jsx";
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

  if (user) return <Navigate to="/overview" replace />;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate(location.state?.from || "/overview", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <LoginBackground />
      <div className="relative z-10 w-full max-w-sm">
        <div className="glass rise space-y-4 p-6" style={{ "--i": 1 }}>
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
              <LogIn className="h-4 w-4" /> {busy ? "Signing in…" : "Sign in"}
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
    </div>
  );
}