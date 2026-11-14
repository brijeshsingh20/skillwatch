import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, Undo2, UploadCloud } from "lucide-react";
import { api, errorMessage } from "../api.js";
import FrameImage from "../components/FrameImage.jsx";
import { Card, ErrorBox, Spinner, TYPE_LABELS } from "../components/ui.jsx";
import { useFetch } from "../hooks.js";

const TYPES = [
  { key: "chair", label: "Chair", color: "#16a34a" },
  { key: "workbench", label: "Workbench", color: "#2563eb" },
  { key: "machine", label: "Machine", color: "#ea580c" },
];
const COLOR = Object.fromEntries(TYPES.map((t) => [t.key, t.color]));
const MIN_PX = 8;

/** The photo with drag-to-draw boxes. Boxes are stored in the photo's own pixels, whatever size it is shown at. */
function ZoneEditor({ src, zones, setZones, activeType }) {
  const imgRef = useRef(null);
  const [natural, setNatural] = useState({ w: 0, h: 0 });
  const [draft, setDraft] = useState(null); // {x0,y0,x1,y1} in natural px

  const toNatural = (e) => {
    const r = imgRef.current.getBoundingClientRect();
    const clamp = (v, max) => Math.max(0, Math.min(max, v));
    return {
      x: clamp(((e.clientX - r.left) / r.width) * natural.w, natural.w),
      y: clamp(((e.clientY - r.top) / r.height) * natural.h, natural.h),
    };
  };
  const down = (e) => {
    if (!natural.w) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = toNatural(e);
    setDraft({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
  };
  const move = (e) => draft && setDraft({ ...draft, ...(({ x, y }) => ({ x1: x, y1: y }))(toNatural(e)) });
  const up = () => {
    if (!draft) return;
    const x = Math.round(Math.min(draft.x0, draft.x1));
    const y = Math.round(Math.min(draft.y0, draft.y1));
    const w = Math.round(Math.abs(draft.x1 - draft.x0));
    const h = Math.round(Math.abs(draft.y1 - draft.y0));
    if (w >= MIN_PX && h >= MIN_PX) setZones((z) => [...z, { item_type: activeType, box: [x, y, w, h] }]);
    setDraft(null);
  };

  const pct = (b) => ({
    left: `${(b[0] / natural.w) * 100}%`, top: `${(b[1] / natural.h) * 100}%`,
    width: `${(b[2] / natural.w) * 100}%`, height: `${(b[3] / natural.h) * 100}%`,
  });
  const draftBox = draft && [Math.min(draft.x0, draft.x1), Math.min(draft.y0, draft.y1), Math.abs(draft.x1 - draft.x0), Math.abs(draft.y1 - draft.y0)];

  return (
    <div className="relative select-none overflow-hidden rounded-md border border-slate-300" style={{ touchAction: "none" }}>
      <img
        ref={imgRef} src={src} alt="Empty workplace" draggable={false} className="block w-full"
        onLoad={(e) => setNatural({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
      />
      <div className="absolute inset-0 cursor-crosshair" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => setDraft(null)}>
        {natural.w > 0 && zones.map((z, i) => (
          <div key={i} className="absolute border-2" style={{ ...pct(z.box), borderColor: COLOR[z.item_type], background: `${COLOR[z.item_type]}22` }}>
            <span className="absolute -top-0.5 left-0 rounded-br px-1 text-[10px] font-semibold text-white" style={{ background: COLOR[z.item_type] }}>{i + 1}</span>
          </div>
        ))}
        {natural.w > 0 && draftBox && (
          <div className="absolute border-2 border-dashed" style={{ ...pct(draftBox), borderColor: COLOR[activeType] }} />
        )}
      </div>
    </div>
  );
}

function StoredMedia({ observationId }) {
  const [media, setMedia] = useState(null);
  const [error, setError] = useState("");
  const load = async () => {
    try {
      setMedia((await api.get(`/observations/${observationId}/media`)).data);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  if (error) return <ErrorBox message={error} />;
  if (!media) return <button className="btn-secondary" onClick={load}>Show stored video and photo</button>;
  return (
    <div className="space-y-2">
      {media.video_url && <video className="w-full rounded" src={media.video_url} controls preload="metadata" />}
      {media.photo_url && <img className="w-full rounded" src={media.photo_url} alt="Empty-room reference" />}
    </div>
  );
}

function ResultCard({ result }) {
  const rows = Object.keys(result.sanctioned || {}).sort();
  const claimed = result.claimed_count;
  return (
    <Card title="Analysis result">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <FrameImage observationId={result.observation_id} />
          {result.stored_in_cloud && <StoredMedia observationId={result.observation_id} />}
        </div>
        <div className="space-y-3 text-sm">
          <div>
            <div className="text-slate-500">People seen (estimate)</div>
            <div className="text-3xl font-bold">{result.estimated_count}</div>
            <div className="text-slate-600">
              {claimed === null || claimed === undefined ? "No attendance claim was found for this date, so nothing to compare." : `Claimed attendance: ${claimed}`}
            </div>
          </div>
          {rows.length > 0 && (
            <table className="w-full text-left">
              <thead className="text-xs text-slate-500"><tr><th>Item</th><th>Sanctioned</th><th>Seen</th><th>Missing</th></tr></thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t} className="border-t border-slate-100">
                    <td className="py-1">{TYPE_LABELS[t] || t}</td>
                    <td>{result.sanctioned[t]}</td>
                    <td>{result.items_detected?.[t] ?? 0}</td>
                    <td className={result.items_missing?.[t] ? "font-semibold text-red-600" : ""}>{result.items_missing?.[t] ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {result.notes?.map((n, i) => <p key={i} className="rounded bg-amber-50 p-2 text-amber-800">{n}</p>)}
          <p className="text-slate-600">
            {result.new_alerts ? `${result.new_alerts} new alert(s) raised. ` : "No new alerts. "}
            Equipment results are what the camera apparently shows, not verified facts.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link className="btn-primary" to={`/centres/${result.centre_id}`}>Open centre dashboard</Link>
            <Link className="btn-secondary" to="/alerts">View alerts</Link>
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function Upload() {
  const { data: centres, error, loading, reload } = useFetch(async () => (await api.get("/centres")).data);
  const [centreId, setCentreId] = useState("");
  const [video, setVideo] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [zones, setZones] = useState([]);
  const [activeType, setActiveType] = useState("chair");
  const [sessionDate, setSessionDate] = useState("");
  const [lowBw, setLowBw] = useState(false);
  const [phase, setPhase] = useState({ state: "idle", message: "", pct: 0 });
  const [result, setResult] = useState(null);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!photo) return undefined;
    const url = URL.createObjectURL(photo);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const poll = useCallback(async (jobId) => {
    try {
      const { data } = await api.get(`/pipeline/jobs/${jobId}`);
      if (data.status === "queued" || data.status === "running") {
        timer.current = setTimeout(() => poll(jobId), 1500);
        return;
      }
      if (data.status === "done" && data.results[0]) {
        setResult(data.results[0]);
        setPhase({ state: "done", message: "Analysis finished.", pct: 100 });
      } else {
        setPhase({ state: "failed", message: data.error || "Analysis failed.", pct: 0 });
      }
    } catch (e) {
      setPhase({ state: "failed", message: errorMessage(e), pct: 0 });
    }
  }, []);

  const busy = phase.state === "uploading" || phase.state === "analysing";
  const ready = centreId && video && photo && !busy;

  const submit = async () => {
    setResult(null);
    setPhase({ state: "uploading", message: "Uploading…", pct: 0 });
    const fd = new FormData();
    fd.append("centre_id", centreId);
    fd.append("video", video);
    fd.append("reference", photo);
    fd.append("zones", JSON.stringify({ zones }));
    fd.append("profile", lowBw ? "lowbw" : "normal");
    if (sessionDate) fd.append("session_date", sessionDate);
    try {
      const { data } = await api.post("/pipeline/upload", fd, {
        onUploadProgress: (e) => e.total && setPhase({ state: "uploading", message: "Uploading…", pct: Math.round((e.loaded / e.total) * 100) }),
      });
      setPhase({ state: "analysing", message: "Analysing the footage…", pct: 100 });
      poll(data.job_id);
    } catch (e) {
      setPhase({ state: "failed", message: errorMessage(e), pct: 0 });
    }
  };

  if (loading && !centres) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analyse uploaded footage</h1>
        <p className="text-sm text-slate-600">
          Upload a CCTV clip and a photo of the same workplace with nobody in it (same camera view). The result is saved as a normal
          observation on the centre&apos;s dashboard. The uploaded video and photo are deleted after analysis; only a blurred sample frame and the counts are kept.
        </p>
      </div>

      <Card title="1. Centre and files">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">Centre
            <select className="input mt-1" value={centreId} onChange={(e) => setCentreId(e.target.value)}>
              <option value="">Select a centre…</option>
              {centres.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.name}</option>)}
            </select>
          </label>
          <label className="block text-sm">Session date (to match the attendance claim)
            <input type="date" className="input mt-1" value={sessionDate} onChange={(e) => setSessionDate(e.target.value)} />
            <span className="text-xs text-slate-500">Leave empty for today.</span>
          </label>
          <label className="block text-sm">CCTV clip (MP4, MOV, AVI, MKV, WebM)
            <input type="file" accept="video/*,.mkv" className="input mt-1" onChange={(e) => setVideo(e.target.files[0] || null)} />
          </label>
          <label className="block text-sm">Photo of the empty workplace (JPG or PNG)
            <input type="file" accept="image/jpeg,image/png" className="input mt-1" onChange={(e) => { setPhoto(e.target.files[0] || null); setZones([]); }} />
          </label>
        </div>
      </Card>

      {photoUrl && (
        <Card title="2. Mark the equipment (optional)">
          <p className="mb-3 text-sm text-slate-600">
            Pick a type, then drag a box around each chair, workbench or machine in the photo. Types you do not mark are not checked.
            Without any boxes, only the head-count is analysed.
          </p>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {TYPES.map((t) => (
              <button key={t.key} type="button" onClick={() => setActiveType(t.key)}
                className={`rounded-md border px-3 py-1.5 text-sm ${activeType === t.key ? "text-white" : "bg-white text-slate-700"}`}
                style={activeType === t.key ? { background: t.color, borderColor: t.color } : { borderColor: t.color }}>
                {t.label} ({zones.filter((z) => z.item_type === t.key).length})
              </button>
            ))}
            <button type="button" className="btn-secondary" disabled={!zones.length} onClick={() => setZones((z) => z.slice(0, -1))}><Undo2 className="h-4 w-4" /> Undo</button>
            <button type="button" className="btn-secondary" disabled={!zones.length} onClick={() => setZones([])}><Trash2 className="h-4 w-4" /> Clear</button>
          </div>
          <ZoneEditor src={photoUrl} zones={zones} setZones={setZones} activeType={activeType} />
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <button className="btn-primary" disabled={!ready} onClick={submit}><UploadCloud className="h-4 w-4" /> Upload and analyse</button>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={lowBw} onChange={(e) => setLowBw(e.target.checked)} /> Low-bandwidth mode
        </label>
        {phase.state !== "idle" && (
          <span className={`text-sm ${phase.state === "failed" ? "text-red-600" : "text-slate-600"}`}>
            {phase.message}{phase.state === "uploading" ? ` ${phase.pct}%` : ""}
          </span>
        )}
      </div>
      {phase.state === "uploading" && <div className="h-2 w-full rounded bg-slate-200"><div className="h-2 rounded bg-indigo-600" style={{ width: `${phase.pct}%` }} /></div>}

      {result && <ResultCard result={result} />}
    </div>
  );
}
