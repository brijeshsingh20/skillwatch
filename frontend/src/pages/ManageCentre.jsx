import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Plus, Save, Trash2 } from "lucide-react";
import { api, errorMessage } from "../api.js";
import { Card, ErrorBox, Spinner } from "../components/ui.jsx";
import {
  DAYS, DetailsFields, EquipmentFields, Notice, inventoryPayload, inventoryValues, toNumberOrNull,
} from "../components/centreFields.jsx";
import { useFetch } from "../hooks.js";

const NEW_BATCH = { name: "", start_time: "09:00", end_time: "13:00", days: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], enrolled: "" };

function DetailsCard({ centre, onSaved }) {
  const [form, setForm] = useState({
    name: centre.name, district: centre.district, state: centre.state, approved_capacity: String(centre.approved_capacity),
    latitude: centre.latitude ?? "", longitude: centre.longitude ?? "",
  });
  const [msg, setMsg] = useState(null);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function save(e) {
    e.preventDefault();
    setMsg(null);
    try {
      await api.patch(`/centres/${centre.id}`, {
        name: form.name.trim(), district: form.district.trim(), state: form.state.trim(),
        approved_capacity: Number(form.approved_capacity),
        latitude: toNumberOrNull(form.latitude), longitude: toNumberOrNull(form.longitude),
      });
      setMsg({ ok: true, text: "Details saved." });
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  return (
    <Card title="Centre details">
      <form onSubmit={save}>
        <DetailsFields form={form} set={set} />
        <button className="btn-primary mt-4"><Save className="h-4 w-4" /> Save details</button>
        <Notice msg={msg} />
      </form>
    </Card>
  );
}

function EquipmentCard({ centre, onSaved }) {
  const [values, setValues] = useState(inventoryValues(centre.inventory));
  const [msg, setMsg] = useState(null);

  async function save(e) {
    e.preventDefault();
    setMsg(null);
    try {
      await api.put(`/centres/${centre.id}/inventory`, inventoryPayload(values));
      setMsg({ ok: true, text: "Equipment numbers saved. They apply from the next analysis." });
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  return (
    <Card title="Equipment this centre should have">
      <form onSubmit={save}>
        <EquipmentFields values={values} setValues={setValues} />
        <button className="btn-primary mt-4"><Save className="h-4 w-4" /> Save equipment</button>
        <Notice msg={msg} />
      </form>
    </Card>
  );
}

function BatchesCard({ centre, onSaved }) {
  const [form, setForm] = useState(NEW_BATCH);
  const [msg, setMsg] = useState(null);

  const toggleDay = (day) =>
    setForm({ ...form, days: form.days.includes(day) ? form.days.filter((d) => d !== day) : [...form.days, day] });

  async function add(e) {
    e.preventDefault();
    setMsg(null);
    if (form.end_time <= form.start_time) return setMsg({ ok: false, text: "The end time must be after the start time." });
    if (form.days.length === 0) return setMsg({ ok: false, text: "Choose at least one day." });
    try {
      await api.post(`/centres/${centre.id}/batches`, {
        name: form.name.trim(), start_time: form.start_time, end_time: form.end_time,
        days: DAYS.filter((d) => form.days.includes(d)).join(","), enrolled: Number(form.enrolled),
      });
      setForm(NEW_BATCH);
      setMsg({ ok: true, text: "Batch added." });
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  async function remove(batch) {
    if (!window.confirm(`Remove the batch "${batch.name}"? Its attendance records will be deleted too.`)) return;
    try {
      await api.delete(`/centres/${centre.id}/batches/${batch.id}`);
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  return (
    <Card title="Batches (class timings)">
      {centre.batches.length === 0 ? (
        <p className="mb-4 text-sm text-slate-500">No batches yet.</p>
      ) : (
        <div className="mb-5 overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100">
          <thead><tr>{["Batch", "Time", "Days", "Enrolled", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {centre.batches.map((b) => (
              <tr key={b.id}>
                <td className="td">{b.name}</td>
                <td className="td">{b.start_time.slice(0, 5)} – {b.end_time.slice(0, 5)}</td>
                <td className="td">{b.days}</td>
                <td className="td">{b.enrolled}</td>
                <td className="td text-right">
                  <button className="inline-flex items-center gap-1 text-sm text-red-600 hover:underline" onClick={() => remove(b)}>
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
      <form onSubmit={add} className="space-y-3 border-t border-slate-100 pt-4">
        <h3 className="text-sm font-semibold text-slate-700">Add a batch</h3>
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="text-sm sm:col-span-2">Batch name
            <input className="input mt-1" required maxLength={120} placeholder="e.g. Morning batch" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="text-sm">Starts
            <input className="input mt-1" type="time" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
          </label>
          <label className="text-sm">Ends
            <input className="input mt-1" type="time" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {DAYS.map((d) => (
            <label key={d} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={form.days.includes(d)} onChange={() => toggleDay(d)} /> {d}
            </label>
          ))}
          <label className="ml-auto flex items-center gap-2 text-sm">Trainees enrolled
            <input className="input w-24" type="number" required min={0} max={10000} value={form.enrolled} onChange={(e) => setForm({ ...form, enrolled: e.target.value })} />
          </label>
        </div>
        <button className="btn-primary"><Plus className="h-4 w-4" /> Add batch</button>
        <Notice msg={msg} />
      </form>
    </Card>
  );
}

function DangerCard({ centre }) {
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const [msg, setMsg] = useState(null);

  async function remove() {
    try {
      await api.delete(`/centres/${centre.id}`);
      navigate("/centres");
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  return (
    <Card title="Delete this centre">
      <p className="mb-3 text-sm text-slate-600">
        This permanently deletes the centre with all its batches, attendance records, analysis results and alerts. It cannot be undone.
        To confirm, type the centre code <b>{centre.code}</b>.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <input className="input max-w-xs" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={centre.code} />
        <button className="btn border border-red-300 bg-white text-red-700 hover:bg-red-50" disabled={typed.trim().toUpperCase() !== centre.code} onClick={remove}>
          <Trash2 className="h-4 w-4" /> Delete centre
        </button>
      </div>
      <Notice msg={msg} />
    </Card>
  );
}

export default function ManageCentre() {
  const { id } = useParams();
  const created = Boolean(useLocation().state?.created);
  const { data: centre, error, loading, reload } = useFetch(() => api.get(`/centres/${id}`).then((r) => r.data), [id]);

  if (loading && !centre) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <Link to={`/centres/${centre.id}`} className="text-sm text-indigo-600 hover:underline">← Back to {centre.name}</Link>
        <h1 className="text-2xl font-bold">Manage {centre.name} <span className="text-base font-normal text-slate-400">{centre.code}</span></h1>
        {created && <div className="mt-2 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">Centre created. Now add its batches below.</div>}
      </div>
      {/* key: forms restart from the saved values after a reload */}
      <DetailsCard key={`d${JSON.stringify([centre.name, centre.district, centre.state, centre.approved_capacity, centre.latitude, centre.longitude])}`} centre={centre} onSaved={reload} />
      <EquipmentCard key={`e${JSON.stringify(centre.inventory)}`} centre={centre} onSaved={reload} />
      <BatchesCard centre={centre} onSaved={reload} />
      <DangerCard centre={centre} />
    </div>
  );
}
