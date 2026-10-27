"use client";

import { useEffect, useMemo, useState } from "react";
import { getScatter, type ScatterPoint } from "@/lib/api";
import { SCATTER_CATALOG, linreg, fiveNum, niceScale } from "@/lib/explore";
import { useLang } from "@/lib/i18n";
import ScatterWithMarginals, { type TeamBox } from "@/components/ScatterWithMarginals";
import TeamPicker from "@/components/TeamPicker";
import PageGuide from "@/components/PageGuide";

// Marginal box plots stay readable up to about this many teams.
const MAX_BOX_TEAMS = 6;

function StatSelect({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  const { t } = useLang();
  return (
    <label>
      {label}:{" "}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {SCATTER_CATALOG.map((c) => (
          <optgroup key={c.category} label={t.explore.categories[c.category] ?? c.category}>
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

export default function ScatterContent() {
  const { t } = useLang();
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

  // Nickname -> tricode, derived from each team's own points: the winner field
  // is this team's tricode on a win, the other side's on a loss.
  const tricodes = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of points ?? []) {
      if (!p.team || m.has(p.team) || !p.home_team || !p.away_team || !p.winner) continue;
      const own = p.wl === "W" ? p.winner : p.home_team === p.winner ? p.away_team : p.home_team;
      m.set(p.team, own);
    }
    return m;
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

  const toPt = (p: ScatterPoint) => ({
    x: p.x as number,
    y: p.y as number,
    team: p.team,
    date: p.game_date,
    home: p.home_team,
    away: p.away_team,
    winner: p.winner,
  });
  const wins = visible.filter((p) => p.wl === "W").map(toPt);
  const losses = visible.filter((p) => p.wl !== "W").map(toPt);

  const trend = useMemo(() => {
    if (!showTrend || visible.length < 2) return null;
    const fit = linreg(visible.map((p) => ({ x: p.x as number, y: p.y as number })));
    if (!fit) return null;
    const xs = visible.map((p) => p.x as number);
    const x1 = Math.min(...xs);
    const x2 = Math.max(...xs);
    return { x1, y1: fit.slope * x1 + fit.intercept, x2, y2: fit.slope * x2 + fit.intercept };
  }, [visible, showTrend]);

  // Shared axis scales so the scatter and its marginal strips line up exactly.
  const domains = useMemo(() => {
    if (visible.length === 0) return null;
    const xs = visible.map((p) => p.x as number);
    const ys = visible.map((p) => p.y as number);
    return {
      x: niceScale(Math.min(...xs), Math.max(...xs)),
      y: niceScale(Math.min(...ys), Math.max(...ys)),
    };
  }, [visible]);

  // One W/L box-plot pair per selected team, per axis.
  const boxes = useMemo<TeamBox[]>(() => {
    return teams.slice(0, MAX_BOX_TEAMS).map((team) => {
      const pts = visible.filter((p) => p.team === team);
      const w = pts.filter((p) => p.wl === "W");
      const l = pts.filter((p) => p.wl !== "W");
      return {
        team,
        tricode: tricodes.get(team) ?? team.slice(0, 3).toUpperCase(),
        xW: fiveNum(w.map((p) => p.x as number)),
        xL: fiveNum(l.map((p) => p.x as number)),
        yW: fiveNum(w.map((p) => p.y as number)),
        yL: fiveNum(l.map((p) => p.y as number)),
      };
    });
  }, [teams, visible, tricodes]);

  return (
    <section>
      <h1>{t.scatter.title}</h1>
      <p className="subtle">{t.scatter.subtitle}</p>

      <div className="controls explore-controls">
        <StatSelect label="X" value={x} onChange={setX} />
        <StatSelect label="Y" value={y} onChange={setY} />
        <label className="inline">
          <input
            type="checkbox"
            checked={showTrend}
            onChange={(e) => setShowTrend(e.target.checked)}
          />{" "}
          {t.scatter.trendline}
        </label>
      </div>
      <TeamPicker
        options={availableTeams}
        selected={teams}
        onChange={setTeams}
        legend={t.scatter.teamsOptional}
        clearLabel={t.explore.clearTeams(teams.length)}
      />

      {error && <p className="status error">{t.scatter.errLoad(error)}</p>}
      {!error && !points && <p className="status">{t.scatter.loading}</p>}
      {!error && points && visible.length === 0 && (
        <p className="status">{t.scatter.noSelection}</p>
      )}
      {!error && points && visible.length > 0 && domains && (
        <>
          <h2>{t.scatter.heading(y, x, visible.length, teams.length)}</h2>
          <ScatterWithMarginals
            wins={wins}
            losses={losses}
            xLabel={x}
            yLabel={y}
            trend={trend}
            xDomain={domains.x.domain}
            yDomain={domains.y.domain}
            xTicks={domains.x.ticks}
            yTicks={domains.y.ticks}
            boxes={boxes}
          />
          {boxes.length > 0 && (
            <p className="caption">
              {t.scatter.margCaption}
              {teams.length > MAX_BOX_TEAMS ? ` ${t.scatter.margCapNote(MAX_BOX_TEAMS)}` : ""}
            </p>
          )}
        </>
      )}
      <PageGuide page="scatter" />
    </section>
  );
}
