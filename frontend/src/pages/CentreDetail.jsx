import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Play, Settings, Upload } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "../api.js";
import { ROLES, useAuth } from "../auth.jsx";
import { AXIS, GRID, LEGEND, TOOLTIP } from "../components/chartTheme.js";
import FrameImage from "../components/FrameImage.jsx";
import { CameraBadge, Card, Cube3D, ErrorBox, KpiCard, SeverityBadge, Spinner, TYPE_LABELS, fmtDateTime } from "../components/ui.jsx";
import { useFetch, usePipelineRun } from "../hooks.js";

function AttendanceForms({ centre, onSaved }) {
  const today = new Date().toISOString().slice(0, 10);
  const [batchId, setBatchId] = useState(centre.batches[0]?.id ?? "");
  const [date, setDate] = useState(today);
  const [count, setCount] = useState("");
  const [msg, setMsg] = useState(null);
  const [file, setFile] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setMsg(null);
    try {
      await api.post("/attendance", { centre_id: centre.id, batch_id: Number(batchId), session_date: date, claimed_count: Number(count) });
      setMsg({ ok: true, text: "Attendance saved." });
      setCount("");
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setMsg(null);
    const form = new FormData();
    form.append("centre_id", centre.id);
    form.append("file", file);
    try {
      const { data } = await api.post("/attendance/csv", form);
      const problems = data.errors.length ? ` ${data.errors.length} row(s) skipped: ${data.errors.slice(0, 3).map((x) => `row ${x.row}: ${x.error}`).join("; ")}` : "";
      setMsg({ ok: data.errors.length === 0, text: `${data.created} added, ${data.updated} updated.${problems}` });
      setFile(null);
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  if (centre.batches.length === 0) return <div className="text-sm text-slate-400">Add a batch to this centre before submitting attendance.</div>;
  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
        <label className="text-sm text-slate-300">Batch
          <select className="input mt-1" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
            {centre.batches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-300">Session date
          <input className="input mt-1" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="text-sm text-slate-300">Present (claimed)
          <input className="input mt-1" type="number" min="0" required value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <div className="flex items-end"><button className="btn-primary">Submit</button></div>
      </form>
      <form onSubmit={upload} className="flex flex-wrap items-center gap-3 border-t border-white/10 pt-3">
        <input
          type="file"
          accept=".csv,text/csv"
          className="text-sm text-slate-300 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-cobalt/40"
          onChange={(e) => setFile(e.target.files[0] || null)}
        />
        <button className="btn-secondary" disabled={!file}><Upload className="h-4 w-4" /> Upload CSV</button>
        <span className="text-xs text-slate-400">Columns: session_date, claimed_count, batch</span>
      </form>
      {msg && <div className={`text-sm ${msg.ok ? "text-acid" : "text-red-400"}`}>{msg.text}</div>}
    </div>
  );
}

/** Inventory rows for one observation (same rules as the server: a type is "checked" if it was seen or found short). */
function inventoryFor(centre, o) {
  const checked = new Set([...Object.keys(o?.items_detected || {}), ...Object.keys(o?.items_missing || {})]);
  return [...centre.inventory]
    .sort((x, y) => x.item_type.localeCompare(y.item_type))
    .map((item) => {
      const t = item.item_type;
      if (!o || !checked.has(t)) return { item_type: t, sanctioned: item.quantity, detected: null, missing: null, not_operable: null };
      return {
        item_type: t,
        sanctioned: item.quantity,
        detected: o.items_detected?.[t] ?? 0,
        missing: o.items_missing?.[t] ?? 0,
        not_operable: o.items_not_operable?.[t] ?? 0,
      };
    });
}

/** Annotated frame with a picker for earlier observations (newest first). The page state lives in CentreDetail. */
function FrameHistory({ rows, view, latestId, onSelect }) {
  const list = rows.length ? rows : [view];
  const index = Math.max(0, list.findIndex((o) => o.id === view.id));
  const optionLabel = (o) => `${o.id === latestId ? "Latest · " : ""}${fmtDateTime(o.captured_at)} · ~${o.estimated_count} people`;

  return (
    <>
      {list.length > 1 && (
        <div className="mb-3 flex items-center gap-2">
          <button type="button" className="btn-secondary" title="Older" disabled={index >= list.length - 1}
            onClick={() => onSelect(list[index + 1].id)}>
            <ChevronLeft className="h-4 w-4" />
          </button>
          <select className="input min-w-0 flex-1" value={view.id} onChange={(e) => onSelect(Number(e.target.value))}>
            {list.map((o) => <option key={o.id} value={o.id}>{optionLabel(o)}</option>)}
          </select>
          <button type="button" className="btn-secondary" title="Newer" disabled={index === 0}
            onClick={() => onSelect(list[index - 1].id)}>
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
      <div className="overflow-hidden rounded-xl border border-white/10">
        <FrameImage observationId={view.has_frame ? view.id : null} />
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Green = present, red = missing, orange = apparently not operable. People are pixelated before the image is saved.
        {" "}Captured {fmtDateTime(view.captured_at)}.
      </p>
    </>
  );
}

export default function CentreDetail() {
  const { id } = useParams();
  const { hasRole } = useAuth();
  const { data, error, loading, reload } = useFetch(() => api.get(`/centres/${id}/detail`).then((r) => r.data), [id]);
  const { status, start } = usePipelineRun(reload);
  const [lowBw, setLowBw] = useState(false);
  const latestId = data?.latest_observation?.id ?? null;
  const { data: history } = useFetch(
    () => api.get(`/centres/${id}/observations`, { params: { limit: 60 } }).then((r) => r.data),
    [id, latestId],
  );
  const [selectedId, setSelectedId] = useState(null);
  useEffect(() => setSelectedId(null), [latestId]); // a new analysis jumps back to the latest observation

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;

  const { centre, compliance_score: score, latest_observation: obs, timeline, open_alerts: alerts } = data;
  const rows = history || [];
  const view = (selectedId && rows.find((o) => o.id === selectedId)) || obs; // the observation every panel below describes
  const isLatest = !view || !obs || view.id === obs.id;
  const viewScore = isLatest ? score : (view.compliance_score ?? null);
  const viewInventory = inventoryFor(centre, view);
  const canRun = hasRole(ROLES.SUPER, ROLES.OFFICER);
  const canSubmit = hasRole(ROLES.SUPER, ROLES.CENTRE);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-4">
          <Cube3D size={40} />
          <div>
            <Link to="/centres" className="link text-sm">← All centres</Link>
            <h1 className="text-3xl font-bold tracking-tight text-white">{centre.name} <span className="text-base font-normal text-slate-500">{centre.code}</span></h1>
            <div className="mt-1 flex items-center gap-2 text-sm text-slate-400">
              {centre.district}, {centre.state} · capacity {centre.approved_capacity} · <CameraBadge status={centre.camera_status} />
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {hasRole(ROLES.SUPER) && (
            <Link to={`/centres/${centre.id}/manage`} className="btn-secondary"><Settings className="h-4 w-4" /> Manage centre</Link>
          )}
          {canRun && (
            <div className="flex flex-wrap items-center gap-3">
              {status.state !== "idle" && <span className="text-sm text-slate-300">{status.message}</span>}
              <label className="flex items-center gap-1.5 text-sm text-slate-300">
                <input type="checkbox" checked={lowBw} onChange={(e) => setLowBw(e.target.checked)} /> Low-bandwidth mode
              </label>
              <button className="btn-primary" disabled={status.state === "running"} onClick={() => start(centre.id, lowBw ? "lowbw" : "normal")}>
                <Play className="h-4 w-4" /> Analyse this centre
              </button>
            </div>
          )}
        </div>
      </div>

      {!isLatest && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-300">
          <span>Showing the observation from {fmtDateTime(view.captured_at)} (session {view.session_date}).</span>
          <button type="button" className="link" onClick={() => setSelectedId(null)}>Back to latest</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard index={0} label="Compliance" value={viewScore === null || viewScore === undefined ? "—" : viewScore} tone={viewScore == null ? "neutral" : viewScore >= 90 ? "good" : viewScore >= 70 ? "warn" : "bad"} />
        <KpiCard index={1} label="Claimed present" value={view?.claimed_count ?? "—"} hint={isLatest ? "Latest session" : `Session ${view.session_date}`} />
        <KpiCard index={2} label="Estimated by camera" value={view ? `~${view.estimated_count}` : "—"} hint={view ? `confidence ${Math.round(view.confidence * 100)}%` : undefined} />
        <KpiCard index={3} label="Discrepancy" value={view ? view.discrepancy_score.toFixed(2) : "—"} tone={view && view.discrepancy_score > 0 ? "bad" : "good"} hint="0 = consistent, 1 = far apart" />
      </div>

      <Card index={4} title="Claimed vs estimated attendance">
        {timeline.length === 0 ? (
          <div className="text-sm text-slate-400">No attendance data yet.</div>
        ) : (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeline}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" minTickGap={24} {...AXIS} />
                <YAxis allowDecimals={false} {...AXIS} />
                <Tooltip {...TOOLTIP} />
                <Legend {...LEGEND} />
                <Line type="monotone" dataKey="claimed" name="Claimed by centre" stroke="#3B6BFF" strokeWidth={2.5} activeDot={{ r: 6 }} connectNulls />
                <Line type="monotone" dataKey="estimated" name="Estimated by camera" stroke="#C6FF00" strokeWidth={2.5} activeDot={{ r: 6 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card index={5} title="Inventory compliance (apparent, not verified)">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-white/10">
            <thead><tr>{["Item", "Sanctioned", "Seen", "Status"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-white/5">
              {viewInventory.map((row, i) => (
                <tr key={row.item_type} className="rise transition-colors hover:bg-white/5" style={{ "--i": i + 6 }}>
                  <td className="td capitalize">{row.item_type}</td>
                  <td className="td">{row.sanctioned}</td>
                  <td className="td">{row.detected ?? "—"}</td>
                  <td className="td">
                    {row.detected === null ? <span className="text-slate-500">not analysed</span>
                      : row.missing > 0 ? <span className="font-medium text-red-400">{row.missing} missing</span>
                      : row.not_operable > 0 ? <span className="font-medium text-amber-300">{row.not_operable} apparently not operable</span>
                      : <span className="font-medium text-acid">OK</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
        <Card index={6} title="Annotated frames">
          {view
            ? <FrameHistory rows={rows} view={view} latestId={latestId} onSelect={setSelectedId} />
            : <FrameImage observationId={null} />}
        </Card>
      </div>

      <Card index={7} title="Unresolved alerts" action={<Link to={`/alerts?centre=${centre.id}`} className="link text-sm">Open in queue</Link>}>
        {alerts.length === 0 ? <div className="text-sm text-slate-400">No unresolved alerts.</div> : (
          <ul className="divide-y divide-white/10">
            {alerts.map((a, i) => (
              <li key={a.id} className="rise flex items-start gap-3 py-2.5 text-sm" style={{ "--i": i + 8 }}>
                <SeverityBadge value={a.severity} />
                <div><div className="font-medium text-white">{TYPE_LABELS[a.alert_type]}</div><div className="text-slate-300">{a.message}</div></div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {canSubmit && (
        <Card index={8} title="Submit attendance">
          <AttendanceForms centre={centre} onSaved={reload} />
        </Card>
      )}
    </div>
  );
}