/** Shared recharts styling: midnight black surface, electric cobalt blue, acid lime. */
export const COLORS = {
  midnight: "#05070F",
  cobalt: "#2F5BFF",
  cobaltSoft: "#6B8CFF",
  cobaltDeep: "#1F3FCC",
  lime: "#C6FF00",
};

export const GRID = "rgba(107,140,255,0.14)"; // cobalt-tinted, used with a dotted dash
export const GRID_DASH = "2 6";
export const AXIS = {
  tick: { fill: "#8FA0C8", fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: "rgba(107,140,255,0.18)" },
};
export const TOOLTIP = {
  contentStyle: {
    background: "rgba(5,7,15,0.94)",
    backdropFilter: "blur(10px)",
    border: "1px solid rgba(198,255,0,0.45)",
    borderRadius: 12,
    color: "#fff",
    boxShadow: "0 0 24px -4px rgba(198,255,0,0.35)",
  },
  labelStyle: { color: COLORS.lime, fontWeight: 600 },
  itemStyle: { color: "#E6ECFF" },
  cursor: { fill: "rgba(47,91,255,0.10)" },
};
export const LEGEND = { wrapperStyle: { color: "#B6C3E6", fontSize: 12 } };