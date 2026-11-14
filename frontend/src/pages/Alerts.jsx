import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MessageSquare, X } from "lucide-react";
import { api, errorMessage } from "../api.js";
import { ROLES, useAuth } from "../auth.jsx";
import FrameImage from "../components/FrameImage.jsx";
import { Card, ErrorBox, SeverityBadge, Spinner, StatusBadge, TYPE_LABELS, fmtDateTime } from "../components/ui.jsx";
import { useFetch } from "../hooks.js";

const NEXT = {
  open: [["acknowledged", "Acknowledge"], ["resolved", "Resolve"]],
  acknowledged: [["resolved", "Resolve"], ["open", "Move back to open"]],
  resolved: [["open", "Reopen"]],
};

function AlertPanel({ alertId, canReview, onClose, onChanged }) {
  const { data, error, loading, reload } = useFetch(() => api.get(`/alerts/${alertId}`).then((r) => r.data), [alertId]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function run(request) {
    setBusy(true);
    setProblem("");
    try {
      await request();
      setComment("");
      reload();
      onChanged();
    } catch (e) {
      setProblem(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const move = (status) => run(() => api.patch(`/alerts/${alertId}/status`, { status, comment: comment.trim() || null }));
  const addComment = () => run(() => api.post(`/alerts/${alertId}/comments`, { text: comment }));

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/30" onClick={onClose}>
      <aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Alert #{alertId}</h2>
          <button className="btn-secondary" onClick={onClose}><X className="h-4 w-4" /></button>
        </div>
        {loading && !data && <Spinner />}
        {error && <ErrorBox message={error} onRetry={reload} />}
        {data && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge value={data.severity} /> <StatusBadge value={data.status} />
              <span className="font-medium">{TYPE_LABELS[data.alert_type]}</span>
            </div>
            <div className="text-sm">
              <Link className="font-medium text-indigo-600 hover:underline" to={`/centres/${data.centre_id}`}>{data.centre_name}</Link>
              <span className="ml-2 text-slate-400">{data.centre_code}</span>
              <div className="text-xs text-slate-500">Raised {fmtDateTime(data.created_at)} · updated {fmtDateTime(data.updated_at)}</div>
            </div>
            <p className="rounded-md bg-slate-50 p-3 text-sm">{data.message}</p>
            {data.observation_id && <FrameImage observationId={data.observation_id} />}

            <div>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><MessageSquare className="h-4 w-4" /> Officer comments</h3>
              {data.comments.length === 0 && <div className="text-sm text-slate-500">No comments yet.</div>}
              <ul className="space-y-2">
                {data.comments.map((c) => (
                  <li key={c.id} className="rounded-md border border-slate-200 p-2 text-sm">
                    <div className="text-xs text-slate-500">{c.user_name} · {fmtDateTime(c.created_at)}</div>
                    {c.text}
                  </li>
                ))}
              </ul>
            </div>

            {canReview ? (
              <div className="space-y-2 border-t pt-3">
                <textarea className="input" rows={3} placeholder="Add a comment (optional when changing status)" value={comment} onChange={(e) => setComment(e.target.value)} />
                {problem && <div className="text-sm text-red-600">{problem}</div>}
                <div className="flex flex-wrap gap-2">
                  {NEXT[data.status].map(([s, label]) => (
                    <button key={s} className={s === "resolved" ? "btn-primary" : "btn-secondary"} disabled={busy} onClick={() => move(s)}>{label}</button>
                  ))}
                  <button className="btn-secondary" disabled={busy || !comment.trim()} onClick={addComment}>Comment only</button>
                </div>
              </div>
            ) : (
              <div className="border-t pt-3 text-xs text-slate-500">Only monitoring officers and administrators can change alert status.</div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <label className="text-xs font-medium text-slate-500">
      {label}
      <select className="input mt-1" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

export default function Alerts() {
  const { hasRole } = useAuth();
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState(null);
  const filters = { status: params.get("status") || "", severity: params.get("severity") || "", alert_type: params.get("type") || "", centre_id: params.get("centre") || "" };
  const { data, error, loading, reload } = useFetch(() => {
    const query = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    return api.get("/alerts", { params: query }).then((r) => r.data);
  }, [filters.status, filters.severity, filters.alert_type, filters.centre_id]);

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    value ? next.set(key, value) : next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Alert queue</h1>
      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <Select label="Status" value={filters.status} onChange={(v) => setFilter("status", v)} options={[["open", "Open"], ["acknowledged", "Acknowledged"], ["resolved", "Resolved"]]} />
          <Select label="Severity" value={filters.severity} onChange={(v) => setFilter("severity", v)} options={[["high", "High"], ["medium", "Medium"], ["low", "Low"]]} />
          <Select label="Type" value={filters.alert_type} onChange={(v) => setFilter("type", v)} options={Object.entries(TYPE_LABELS)} />
        </div>
        {filters.centre_id && (
          <div className="mt-3 text-sm text-slate-600">
            Showing one centre only. <button className="text-indigo-600 hover:underline" onClick={() => setFilter("centre", "")}>Show all centres</button>
          </div>
        )}
      </Card>

      {loading && !data && <Spinner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <Card>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100">
              <thead><tr>{["Severity", "Type", "Centre", "Status", "Raised"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((a) => (
                  <tr key={a.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setSelected(a.id)}>
                    <td className="td"><SeverityBadge value={a.severity} /></td>
                    <td className="td">{TYPE_LABELS[a.alert_type]}</td>
                    <td className="td">{a.centre_name} <span className="text-xs text-slate-400">{a.centre_code}</span></td>
                    <td className="td"><StatusBadge value={a.status} /></td>
                    <td className="td text-slate-500">{fmtDateTime(a.created_at)}</td>
                  </tr>
                ))}
                {data.length === 0 && <tr><td className="td text-slate-500" colSpan={5}>No alerts match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {selected && <AlertPanel alertId={selected} canReview={hasRole(ROLES.SUPER, ROLES.OFFICER)} onClose={() => setSelected(null)} onChanged={reload} />}
    </div>
  );
}
