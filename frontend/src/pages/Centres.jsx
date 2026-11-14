import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { api } from "../api.js";
import { ROLES, useAuth } from "../auth.jsx";
import { CameraBadge, Card, ErrorBox, ScoreBadge, Spinner, fmtDateTime } from "../components/ui.jsx";
import { useFetch } from "../hooks.js";

export default function Centres() {
  const [query, setQuery] = useState("");
  const { hasRole } = useAuth();
  const { data, error, loading, reload } = useFetch(() => api.get("/centres").then((r) => r.data));

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;

  const q = query.trim().toLowerCase();
  const rows = data.filter((c) => !q || [c.name, c.code, c.district, c.state].some((v) => v.toLowerCase().includes(q)));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Centres</h1>
        {hasRole(ROLES.SUPER) && (
          <Link to="/centres/new" className="btn-primary"><Plus className="h-4 w-4" /> Add centre</Link>
        )}
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <input className="input pl-8" placeholder="Search name, code, district…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead>
              <tr>
                {["Centre", "District", "Camera", "Compliance", "Unresolved alerts", "Last analysed"].map((h) => (
                  <th key={h} className="th">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="td">
                    <Link to={`/centres/${c.id}`} className="font-medium text-indigo-600 hover:underline">{c.name}</Link>
                    <span className="ml-2 text-xs text-slate-400">{c.code}</span>
                  </td>
                  <td className="td">{c.district}, {c.state}</td>
                  <td className="td"><CameraBadge status={c.camera_status} /></td>
                  <td className="td"><ScoreBadge score={c.compliance_score} /></td>
                  <td className="td">{c.open_alerts}</td>
                  <td className="td text-slate-500">{fmtDateTime(c.last_observed_at)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td className="td text-slate-500" colSpan={6}>No centres match.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
