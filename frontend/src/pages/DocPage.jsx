import { api } from "../api.js";
import Markdown from "../components/Markdown.jsx";
import { Card, ErrorBox, Spinner } from "../components/ui.jsx";
import { useFetch } from "../hooks.js";

const MISSING_HINT = {
  accuracy: "The accuracy report has not been generated yet. Run: python -m scripts.evaluate",
  privacy: "The privacy note (docs/PRIVACY.md) has not been written yet.",
};

/** Shows a Markdown document served by the backend (docs/ACCURACY.md or docs/PRIVACY.md). */
export default function DocPage({ name, title }) {
  const { data, error, loading, reload } = useFetch(
    () => api.get(`/reports/${name}`).then((r) => r.data).catch((e) => (e.response?.status === 404 ? { missing: true } : Promise.reject(e))),
    [name]
  );
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{title}</h1>
      {loading && !data && <Spinner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data?.missing && <Card><div className="text-sm text-slate-600">{MISSING_HINT[name]}</div></Card>}
      {data?.markdown && <Card><Markdown source={data.markdown} /></Card>}
    </div>
  );
}
