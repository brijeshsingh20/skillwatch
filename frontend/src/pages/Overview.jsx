import { useState } from "react";
import { Link } from "react-router-dom";
import { Play } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { ROLES, useAuth } from "../auth.jsx";
import { AXIS, COLORS, GRID, GRID_DASH, TOOLTIP } from "../components/chartTheme.js";
import { Card, ErrorBox, KpiCard, ScoreBadge, Spinner, TYPE_LABELS } from "../components/ui.jsx";
import { useFetch, useMediaQuery, usePipelineRun } from "../hooks.js";

// Severity on the brand palette: high = acid lime (glowing), medium = electric cobalt, low = dim cobalt.
const SEV_FILL = { high: "url(#sevHigh)", medium: "url(#sevMedium)", low: "url(#sevLow)" };
const LABEL = { fill: "#FFFFFF", fontSize: 13, fontWeight: 700 };

export default function Overview() {
  const { hasRole } = useAuth();
  const { data, error, loading, reload } = useFetch(async () => {
    const [overview, centres] = await Promise.all([api.get("/dashboard/overview"), api.get("/centres")]);
    return { overview: overview.data, centres: centres.data };
  });
  const { status, start } = usePipelineRun(reload);
  const canRun = hasRole(ROLES.SUPER, ROLES.OFFICER);
  const [lowBw, setLowBw] = useState(false);
  const narrow = useMediaQuery("(max-width: 639px)");

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const { overview, centres } = data;

  const severity = ["high", "medium", "low"].map((k) => ({ name: k, count: overview.open_alerts_by_severity[k] || 0 }));
  const types = Object.entries(overview.open_alerts_by_type).map(([k, v]) => ({ name: TYPE_LABELS[k] || k, count: v }));
  const topCount = Math.max(0, ...types.map((t) => t.count)); // the most common alert type is highlighted in lime
  const worst = [...centres].filter((c) => c.compliance_score !== null).sort((a, b) => a.compliance_score - b.compliance_score).slice(0, 5);
  const avg = overview.average_compliance;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-bold tracking-tight text-white">Overview</h1>
        {canRun && (
          <div className="flex flex-wrap items-center gap-3">
            {status.state !== "idle" && (
              <span className={`text-sm ${status.state === "failed" ? "text-red-400" : "text-slate-300"}`}>{status.message}</span>
            )}
            <label className="flex items-center gap-1.5 text-sm text-slate-300" title="Fewer frames, smaller images, stronger compression">
              <input type="checkbox" checked={lowBw} onChange={(e) => setLowBw(e.target.checked)} /> Low-bandwidth mode
            </label>
            <button className="btn-primary" disabled={status.state === "running"} onClick={() => start(null, lowBw ? "lowbw" : "normal")}>
              <Play className="h-4 w-4" /> Run analysis on all centres
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard index={0} label="Centres monitored" value={overview.centres} />
        <KpiCard
          index={1}
          label="Unresolved alerts"
          value={overview.open_alerts}
          tone={overview.open_alerts ? "bad" : "good"}
          hint={`${overview.centres_with_open_alerts} centre(s) affected`}
        />
        <KpiCard
          index={2}
          label="Average compliance"
          value={avg === null ? "—" : `${avg}`}
          tone={avg === null ? "neutral" : avg >= 90 ? "good" : avg >= 70 ? "warn" : "bad"}
          hint="Out of 100, latest observation per centre"
        />
        <KpiCard index={3} label="Cameras not online" value={overview.cameras_not_online} tone={overview.cameras_not_online ? "warn" : "good"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card index={4} title="Unresolved alerts by severity">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={severity} margin={{ top: 22, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="sevHigh" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS.lime} />
                    <stop offset="100%" stopColor={COLORS.lime} stopOpacity={0.25} />
                  </linearGradient>
                  <linearGradient id="sevMedium" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS.cobaltSoft} />
                    <stop offset="100%" stopColor={COLORS.cobalt} stopOpacity={0.35} />
                  </linearGradient>
                  <linearGradient id="sevLow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS.cobalt} stopOpacity={0.7} />
                    <stop offset="100%" stopColor={COLORS.cobaltDeep} stopOpacity={0.15} />
                  </linearGradient>
                  <filter id="limeGlow" x="-40%" y="-20%" width="180%" height="150%">
                    <feGaussianBlur stdDeviation="6" result="blur" />
                    <feFlood floodColor={COLORS.lime} floodOpacity="0.45" />
                    <feComposite in2="blur" operator="in" />
                    <feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge>
                  </filter>
                </defs>
                <CartesianGrid stroke={GRID} strokeDasharray={GRID_DASH} vertical={false} />
                <XAxis dataKey="name" {...AXIS} />
                <YAxis allowDecimals={false} {...AXIS} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="count" radius={[10, 10, 0, 0]} maxBarSize={64} background={{ fill: "rgba(47,91,255,0.07)", radius: 10 }} animationDuration={900}>
                  {severity.map((s) => (
                    <Cell key={s.name} fill={SEV_FILL[s.name]} filter={s.name === "high" ? "url(#limeGlow)" : undefined} />
                  ))}
                  <LabelList dataKey="count" position="top" {...LABEL} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card index={5} title="Unresolved alerts by type">
          {types.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-400">No unresolved alerts.</div>
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={types} layout="vertical" margin={{ left: narrow ? 0 : 40, right: 28 }}>
                  <defs>
                    <linearGradient id="typeCobalt" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor={COLORS.cobaltDeep} />
                      <stop offset="100%" stopColor={COLORS.cobaltSoft} />
                    </linearGradient>
                    <linearGradient id="typeLime" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor={COLORS.lime} stopOpacity={0.55} />
                      <stop offset="100%" stopColor={COLORS.lime} />
                    </linearGradient>
                    <filter id="limeGlowH" x="-20%" y="-40%" width="150%" height="180%">
                      <feGaussianBlur stdDeviation="5" result="blur" />
                      <feFlood floodColor={COLORS.lime} floodOpacity="0.4" />
                      <feComposite in2="blur" operator="in" />
                      <feMerge><feMergeNode /><feMergeNode in="SourceGraphic" /></feMerge>
                    </filter>
                  </defs>
                  <CartesianGrid stroke={GRID} strokeDasharray={GRID_DASH} horizontal={false} />
                  <XAxis type="number" allowDecimals={false} {...AXIS} />
                  <YAxis type="category" dataKey="name" width={narrow ? 104 : 150} {...AXIS} />
                  <Tooltip {...TOOLTIP} />
                  <Bar dataKey="count" radius={[0, 10, 10, 0]} barSize={26} background={{ fill: "rgba(47,91,255,0.07)", radius: 10 }} animationDuration={900}>
                    {types.map((t) => (
                      <Cell key={t.name} fill={t.count === topCount ? "url(#typeLime)" : "url(#typeCobalt)"} filter={t.count === topCount ? "url(#limeGlowH)" : undefined} />
                    ))}
                    <LabelList dataKey="count" position="right" {...LABEL} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <Card index={6} title="Centres needing attention" action={<Link to="/centres" className="link text-sm">All centres</Link>}>
        {worst.length === 0 ? (
          <div className="text-sm text-slate-400">
            No observations yet. {canRun ? "Run an analysis to populate the dashboard." : "Ask a monitoring officer to run an analysis."}
          </div>
        ) : (
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-white/10">
            <thead>
              <tr>
                <th className="th">Centre</th>
                <th className="th">Compliance</th>
                <th className="th">Unresolved alerts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {worst.map((c, i) => (
                <tr key={c.id} className="rise transition-colors hover:bg-white/5" style={{ "--i": i + 7 }}>
                  <td className="td">
                    <Link to={`/centres/${c.id}`} className="link">
                      {c.name}
                    </Link>
                    <span className="ml-2 text-xs text-slate-500">{c.code}</span>
                  </td>
                  <td className="td"><ScoreBadge score={c.compliance_score} /></td>
                  <td className="td">{c.open_alerts}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>
    </div>
  );
}