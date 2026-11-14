import { useState } from "react";
import { UserPlus } from "lucide-react";
import { api, errorMessage } from "../api.js";
import { ROLE_LABELS } from "../auth.jsx";
import { Card, ErrorBox, Spinner } from "../components/ui.jsx";
import { useFetch } from "../hooks.js";

const EMPTY = { email: "", full_name: "", password: "", role: "monitoring_officer", centre_id: "" };

export default function Users() {
  const users = useFetch(() => api.get("/users").then((r) => r.data));
  const centres = useFetch(() => api.get("/centres").then((r) => r.data));
  const [form, setForm] = useState(EMPTY);
  const [msg, setMsg] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function create(e) {
    e.preventDefault();
    setMsg(null);
    try {
      await api.post("/users", { ...form, centre_id: form.role === "centre_admin" ? Number(form.centre_id) || null : null });
      setForm(EMPTY);
      setMsg({ ok: true, text: "User created." });
      users.reload();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  async function deactivate(u) {
    if (!window.confirm(`Deactivate ${u.email}? They will no longer be able to sign in.`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      users.reload();
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Users</h1>
      <Card title="Add a user">
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm">Full name<input className="input mt-1" required value={form.full_name} onChange={set("full_name")} /></label>
          <label className="text-sm">Email<input className="input mt-1" type="email" required value={form.email} onChange={set("email")} /></label>
          <label className="text-sm">Password (min 8)<input className="input mt-1" type="password" minLength={8} required value={form.password} onChange={set("password")} /></label>
          <label className="text-sm">Role
            <select className="input mt-1" value={form.role} onChange={set("role")}>
              {Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          {form.role === "centre_admin" && (
            <label className="text-sm">Centre
              <select className="input mt-1" required value={form.centre_id} onChange={set("centre_id")}>
                <option value="">Choose…</option>
                {(centres.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
          )}
          <div className="flex items-end"><button className="btn-primary"><UserPlus className="h-4 w-4" /> Create user</button></div>
        </form>
        {msg && <div className={`mt-3 text-sm ${msg.ok ? "text-emerald-700" : "text-red-600"}`}>{msg.text}</div>}
      </Card>

      {users.loading && !users.data && <Spinner />}
      {users.error && <ErrorBox message={users.error} onRetry={users.reload} />}
      {users.data && (
        <Card title="All users">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead><tr>{["Name", "Email", "Role", "Active", ""].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {users.data.map((u) => (
                <tr key={u.id}>
                  <td className="td">{u.full_name}</td>
                  <td className="td">{u.email}</td>
                  <td className="td">{ROLE_LABELS[u.role]}</td>
                  <td className="td">{u.is_active ? "Yes" : "No"}</td>
                  <td className="td text-right">{u.is_active && <button className="text-sm text-red-600 hover:underline" onClick={() => deactivate(u)}>Deactivate</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}
    </div>
  );
}
