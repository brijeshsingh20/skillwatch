import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "./api.js";

/** True while the viewport matches a CSS media query (e.g. "(max-width: 639px)"). */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/** Load data with `loader()` (returns a promise). Re-runs when `deps` change or `reload()` is called. */
export function useFetch(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    loader()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: errorMessage(e), loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

/** Start the vision pipeline and poll the job until it finishes. */
export function usePipelineRun(onFinished) {
  const [status, setStatus] = useState({ state: "idle", message: "" });
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const poll = useCallback(
    async (jobId) => {
      try {
        const { data } = await api.get(`/pipeline/jobs/${jobId}`);
        if (data.status === "queued" || data.status === "running") {
          timer.current = setTimeout(() => poll(jobId), 1500);
          return;
        }
        const base = data.status === "done" ? `Finished: ${data.results.length} centre(s) analysed.` : "Analysis failed.";
        setStatus({ state: data.status, message: data.error ? `${base} ${data.error}` : base });
        if (onFinished) onFinished();
      } catch (e) {
        setStatus({ state: "failed", message: errorMessage(e) });
      }
    },
    [onFinished]
  );

  const start = useCallback(
    async (centreId = null, profile = "normal") => {
      setStatus({ state: "running", message: "Analysis running…" });
      try {
        const { data } = await api.post("/pipeline/run", { centre_id: centreId, profile });
        poll(data.job_id);
      } catch (e) {
        setStatus({ state: "failed", message: errorMessage(e) });
      }
    },
    [poll]
  );
  return { status, start };
}
