import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { api, errorMessage } from "../api.js";
import { Card } from "../components/ui.jsx";
import { DetailsFields, EquipmentFields, Notice, inventoryPayload, toNumberOrNull } from "../components/centreFields.jsx";

const EMPTY = { code: "", name: "", district: "", state: "", approved_capacity: "", latitude: "", longitude: "" };

export default function NewCentre() {
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [equipment, setEquipment] = useState({ chair: "", workbench: "", machine: "" });
  const [msg, setMsg] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setMsg(null);
    setSaving(true);
    try {
      const { data } = await api.post("/centres", {
        code: form.code.trim().toUpperCase(),
        name: form.name.trim(),
        district: form.district.trim(),
        state: form.state.trim(),
        approved_capacity: Number(form.approved_capacity),
        latitude: toNumberOrNull(form.latitude),
        longitude: toNumberOrNull(form.longitude),
        inventory: inventoryPayload(equipment),
        batches: [],
      });
      navigate(`/centres/${data.id}/manage`, { state: { created: true } });
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
      setSaving(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link to="/centres" className="text-sm text-indigo-600 hover:underline">← All centres</Link>
        <h1 className="text-2xl font-bold">Add a training centre</h1>
        <p className="text-sm text-slate-500">You can add the batches (class timings) on the next screen.</p>
      </div>
      <form onSubmit={submit} className="space-y-6">
        <Card title="Centre details">
          <label className="mb-3 block text-sm">Centre code <span className="text-slate-400">(short and unique, e.g. SC006; letters, numbers, - and _ only)</span>
            <input className="input mt-1 max-w-xs uppercase" required minLength={2} maxLength={20} pattern="[A-Za-z0-9_\-]+" value={form.code} onChange={set("code")} />
          </label>
          <DetailsFields form={form} set={set} />
        </Card>
        <Card title="Equipment this centre should have">
          <EquipmentFields values={equipment} setValues={setEquipment} />
        </Card>
        <div>
          <button className="btn-primary" disabled={saving}><Plus className="h-4 w-4" /> {saving ? "Creating…" : "Create centre"}</button>
          <Notice msg={msg} />
        </div>
      </form>
    </div>
  );
}
