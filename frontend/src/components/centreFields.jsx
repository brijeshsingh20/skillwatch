/** Form pieces shared by the "Add centre" and "Manage centre" pages. Plain labels and hints, no technical terms. */

export const ITEMS = [
  ["chair", "Chairs"],
  ["workbench", "Workbenches"],
  ["machine", "Machines"],
];
export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const toNumberOrNull = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

/** Form values {chair: "10", workbench: "", ...} -> the list the server expects. Blank items are left out. */
export function inventoryPayload(values) {
  return ITEMS.filter(([key]) => values[key] !== "" && values[key] !== undefined)
    .map(([key]) => ({ item_type: key, quantity: Number(values[key]) }));
}

/** The server's inventory list -> form values. */
export function inventoryValues(inventory = []) {
  const values = Object.fromEntries(ITEMS.map(([key]) => [key, ""]));
  inventory.forEach((line) => { values[line.item_type] = String(line.quantity); });
  return values;
}

export function Notice({ msg }) {
  if (!msg) return null;
  return <div className={`mt-3 text-sm ${msg.ok ? "text-emerald-700" : "text-red-600"}`}>{msg.text}</div>;
}

export function DetailsFields({ form, set }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm">Centre name
        <input className="input mt-1" required maxLength={160} value={form.name} onChange={set("name")} />
      </label>
      <label className="text-sm">Capacity (how many trainees it is approved for)
        <input className="input mt-1" type="number" required min={1} max={10000} value={form.approved_capacity} onChange={set("approved_capacity")} />
      </label>
      <label className="text-sm">District
        <input className="input mt-1" required maxLength={80} value={form.district} onChange={set("district")} />
      </label>
      <label className="text-sm">State
        <input className="input mt-1" required maxLength={80} value={form.state} onChange={set("state")} />
      </label>
      <label className="text-sm">Latitude <span className="text-slate-400">(optional, e.g. 19.0760)</span>
        <input className="input mt-1" type="number" step="any" min={-90} max={90} value={form.latitude} onChange={set("latitude")} />
      </label>
      <label className="text-sm">Longitude <span className="text-slate-400">(optional, e.g. 72.8777)</span>
        <input className="input mt-1" type="number" step="any" min={-180} max={180} value={form.longitude} onChange={set("longitude")} />
      </label>
    </div>
  );
}

export function EquipmentFields({ values, setValues }) {
  return (
    <div>
      <p className="mb-3 text-sm text-slate-500">
        How many of each item should this centre have? The camera check compares what it sees against these numbers.
        Leave a box empty if that item should not be checked.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        {ITEMS.map(([key, label]) => (
          <label key={key} className="text-sm">{label}
            <input className="input mt-1" type="number" min={0} max={10000} value={values[key]}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
          </label>
        ))}
      </div>
    </div>
  );
}
