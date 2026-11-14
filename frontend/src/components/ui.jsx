import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import "../orb.css";

export const TYPE_LABELS = {
  attendance_mismatch: "Attendance mismatch",
  equipment_missing: "Equipment missing",
  equipment_not_operable: "Equipment not operable",
  camera_offline: "Camera offline",
  low_quality: "Low image quality",
};

/** Backend times are UTC without a "Z"; add it so the browser converts to local time correctly. */
export function parseUtc(iso) {
  if (!iso) return null;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}
export function fmtDateTime(iso) {
  const d = parseUtc(iso);
  return d ? d.toLocaleString() : "—";
}

/** Shimmering placeholder shown while data loads. */
export function Spinner({ label = "Loading…" }) {
  return (
    <div className="space-y-4 p-2" role="status">
      <div className="flex items-center gap-2 text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin text-cobalt-300" /> {label}
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24" />)}
      </div>
      <div className="skeleton h-56" />
    </div>
  );
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-red-400/30 bg-red-500/10 p-4 text-sm text-red-200 backdrop-blur">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-300" />
      <div className="flex-1">{message}</div>
      {onRetry && (
        <button className="btn-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/** Glass card. `index` staggers the entrance animation when several cards load together. */
export function Card({ title, action, children, className = "", index = 0 }) {
  return (
    <section className={`glass glass-lift rise ${className}`} style={{ "--i": index }}>
      {(title || action) && (
        <header className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 className="text-sm font-semibold tracking-wide text-white/90">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const TONES = {
  neutral: "text-white",
  good: "text-acid",
  warn: "text-amber-300",
  bad: "text-red-400",
};

/** Counts a number up from 0 once. Skipped for people who prefer reduced motion. */
function useCountUp(target, duration = 900) {
  const [n, setN] = useState(target === null ? null : 0);
  useEffect(() => {
    if (target === null) return undefined;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setN(target);
      return undefined;
    }
    let raf;
    let start;
    const step = (t) => {
      if (start === undefined) start = t;
      const p = Math.min((t - start) / duration, 1);
      setN(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return n;
}

export function KpiCard({ label, value, hint, tone = "neutral", index = 0 }) {
  const text = String(value);
  const numeric = /^-?\d+(\.\d+)?$/.test(text); // 12, "78.5" count up; "—" and "~12" stay as they are
  const decimals = numeric && text.includes(".") ? text.split(".")[1].length : 0;
  const counted = useCountUp(numeric ? parseFloat(text) : null);
  const shown = numeric && counted !== null ? counted.toFixed(decimals) : value;
  return (
    <div className={`glass glass-tilt rise p-4 ${tone === "bad" && Number(value) > 0 ? "pulse-glow" : ""}`} style={{ "--i": index }}>
      <div className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-1 text-4xl font-semibold tabular-nums ${TONES[tone]}`}>{shown}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

/** Small rotating glass cube, purely decorative. */
/** Animated 3D orb (gyroscope rings, pulsing core, orbiting lights). Purely decorative; tilts with the mouse. */
export function Orb3D({ size = 56 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    let raf = 0;
    const onMove = (e) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = ref.current;
        if (!el) return;
        const x = e.clientX / window.innerWidth - 0.5;
        const y = e.clientY / window.innerHeight - 0.5;
        el.style.setProperty("--tx", `${(-y * 40).toFixed(1)}deg`);
        el.style.setProperty("--ty", `${(x * 50).toFixed(1)}deg`);
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);
  return (
    <div className="orb-scene shrink-0" style={{ "--s": `${size}px` }} aria-hidden="true">
      <div className="orb" ref={ref}>
        <i className="orb-ring r1" />
        <i className="orb-ring r2" />
        <i className="orb-ring r3" />
        <span className="orb-core" />
        <span className="orb-orbit"><b className="orb-dot" /></span>
        <span className="orb-orbit o2"><b className="orb-dot d2" /></span>
      </div>
      <span className="orb-shadow" />
    </div>
  );
}
// The pages still import this name, so nothing else needs to change.
export const Cube3D = Orb3D;

function Pill({ className, children }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}>{children}</span>;
}

const SEVERITY = {
  high: "bg-red-500/15 text-red-300 ring-red-400/30",
  medium: "bg-amber-400/15 text-amber-300 ring-amber-300/30",
  low: "bg-cobalt/25 text-cobalt-300 ring-cobalt-400/40",
};
export const SeverityBadge = ({ value }) => <Pill className={SEVERITY[value] || "bg-white/10 text-slate-300 ring-white/20"}>{value}</Pill>;

const STATUS = {
  open: "bg-red-500/15 text-red-300 ring-red-400/30",
  acknowledged: "bg-amber-400/15 text-amber-300 ring-amber-300/30",
  resolved: "bg-acid/10 text-acid ring-acid/30",
};
export const StatusBadge = ({ value }) => (
  <Pill className={STATUS[value] || "bg-white/10 text-slate-300 ring-white/20"}>
    {value === "open" && <span className="pulse-dot" />}
    {value}
  </Pill>
);

const CAMERA = {
  online: "bg-acid/10 text-acid ring-acid/30",
  low_quality: "bg-amber-400/15 text-amber-300 ring-amber-300/30",
  offline: "bg-red-500/15 text-red-300 ring-red-400/30",
};
export const CameraBadge = ({ status }) => (
  <Pill className={CAMERA[status] || "bg-white/10 text-slate-300 ring-white/20"}>
    {status === "online" && <span className="pulse-dot" />}
    {status.replace("_", " ")}
  </Pill>
);

export function ScoreBadge({ score }) {
  if (score === null || score === undefined) return <span className="text-slate-500">no data</span>;
  const cls =
    score >= 90 ? "bg-acid/10 text-acid ring-acid/30" : score >= 70 ? "bg-amber-400/15 text-amber-300 ring-amber-300/30" : "bg-red-500/15 text-red-300 ring-red-400/30";
  return <Pill className={cls}>{score}/100</Pill>;
}
