// Article chart colors. Kept out of charts.tsx ("use client") so server-rendered
// figure modules get the real values, not client-reference proxies.
// Model colors match the rest of the site (PerfLineChart, accuracy page).
export const ARTICLE_COLORS = {
  rf: "#3b82f6",
  nn: "#22c55e",
  xgb: "#f59e0b",
  market: "#cbd5e1",
  neutral: "#94a3b8", // baseline / control side of a comparison
  accent: "#f97316", // the thing the figure is about
};
