"use client";

import { useEffect, useMemo, useState } from "react";
import { getScatter, type ScatterPoint } from "@/lib/api";
import { SCATTER_CATALOG, linreg } from "@/lib/explore";
import ScatterPlot from "@/components/ScatterPlot";

function StatSelect({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  return (
    <label>
      {label}:{" "}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {SCATTER_CATALOG.map((c) => (
          <optgroup key={c.category} label={c.category}>
            {c.stats.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export default function ScatterPage() {
  const [x, setX] = useState("PTS");
  const [y, setY] = useState("AST");
  const [points, setPoints] = useState<ScatterPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [teams, setTeams] = useState<string[]>([]);
  const [showTrend, setShowTrend] = useState(true);

  useEffect(() => {
    setPoints(null);
    setError(null);
    getScatter(x, y, 365)
      .then((r) => setPoints(r.points))
      .catch((e) => setError(String(e)));
  }, [x, y]);

  const availableTeams = useMemo(() => {
    if (!points) return [];
    const s = new Set<string>();
    for (const p of points) if (p.team) s.add(p.team);
    return [...s].sort();
  }, [points]);

  const visible = useMemo(() => {
    if (!points) return [];
    const tset = new Set(teams);
    return points.filter(
      (p) =>
        p.x !== null &&
        p.y !== null &&
        (teams.length === 0 || (p.team !== null && tset.has(p.team))),
    );
  }, [points, teams]);

  const wins = visible
    .filter((p) => p.wl === "W")
    .map((p) => ({ x: p.x as number, y: p.y as number, team: p.team }));
  const losses = visible
    .filter((p) => p.wl !== "W")
    .map((p) => ({ x: p.x as number, y: p.y as number, team: p.team }));

  const trend = useMemo(() => {
    if (!showTrend || visible.length < 2) return null;
    const fit = linreg(visible.map((p) => ({ x: p.x as number, y: p.y as number })));
    if (!fit) return null;
    const xs = visible.map((p) => p.x as number);
    const x1 = Math.min(...xs);
    const x2 = Math.max(...xs);
    return { x1, y1: fit.slope * x1 + fit.intercept, x2, y2: fit.slope * x2 + fit.intercept };
  }, [visible, showTrend]);

  return (
    <section>
      <h1>Stat scatter</h1>
      <p className="subtle">
        Every team-game as a point — pick two stats, color by win/loss, fit a trendline,
        and optionally filter to specific teams.
      </p>

      <div className="controls explore-controls">
        <StatSelect label="X" value={x} onChange={setX} />
        <StatSelect label="Y" value={y} onChange={setY} />
        <label className="team-select">
          Teams (optional):
          <select
            multiple
            size={5}
            value={teams}
            onChange={(e) => setTeams([...e.target.selectedOptions].map((o) => o.value))}
          >
            {availableTeams.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={showTrend}
            onChange={(e) => setShowTrend(e.target.checked)}
          />{" "}
          Trendline
        </label>
      </div>

      {error && <p className="status error">Couldn&apos;t load: {error}</p>}
      {!error && !points && <p className="status">Loading…</p>}
      {!error && points && visible.length === 0 && (
        <p className="status">No points for this selection.</p>
      )}
      {!error && points && visible.length > 0 && (
        <>
          <h2>
            {y} vs {x} — {visible.length} games
            {teams.length > 0 ? `, ${teams.length} team${teams.length > 1 ? "s" : ""}` : ""}
          </h2>
          <ScatterPlot wins={wins} losses={losses} xLabel={x} yLabel={y} trend={trend} />
        </>
      )}
    </section>
  );
}
