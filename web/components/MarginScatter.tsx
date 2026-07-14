"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { Prediction } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import type { Dict } from "@/lib/translations";

type Pt = {
  x: number; // predicted home-perspective margin
  y: number; // actual home-perspective margin
  date: string;
  home: string;
  away: string;
  pick: string;
  correct: boolean;
};

function PointTooltip({
  active,
  payload,
  t,
}: {
  active?: boolean;
  payload?: Array<{ payload: Pt }>;
  t: Dict;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div
      style={{
        background: "#141a2e",
        border: "1px solid #243049",
        borderRadius: 4,
        padding: "8px 10px",
        fontSize: 12,
        color: "#e7ecf5",
      }}
    >
      <div style={{ color: "#9aa6c0", marginBottom: 2 }}>{p.date}</div>
      <div>
        <strong>{p.away}</strong> @ <strong>{p.home}</strong> · {t.marginScatter.picked(p.pick)}
      </div>
      <div style={{ marginTop: 4, color: "#9aa6c0" }}>
        {t.marginScatter.predActual(
          `${p.x > 0 ? "+" : ""}${p.x.toFixed(1)}`,
          `${p.y > 0 ? "+" : ""}${p.y}`,
        )}
      </div>
    </div>
  );
}

export default function MarginScatter({ rows }: { rows: Prediction[] }) {
  const { t } = useLang();
  const pts: Pt[] = rows
    .filter((r) => r.actual_margin !== null && r.is_correct !== null)
    .map((r) => ({
      x: r.predicted_margin,
      y: r.actual_margin as number,
      date: r.game_date,
      home: r.home_team,
      away: r.away_team,
      pick: r.predicted_winner,
      correct: r.is_correct === true,
    }));
  if (pts.length === 0) return <p className="status">{t.marginScatter.noGraded}</p>;

  const hits = pts.filter((p) => p.correct);
  const misses = pts.filter((p) => !p.correct);

  // Domain snapped outward to 20s; major demarcations every 20, minor lines
  // every 10 (drawn as recessive reference lines — fainter than the major grid).
  const all = pts.flatMap((p) => [p.x, p.y]);
  const lo = Math.floor(Math.min(...all) / 20) * 20;
  const hi = Math.ceil(Math.max(...all) / 20) * 20;
  const majors: number[] = [];
  for (let v = lo; v <= hi; v += 20) majors.push(v);
  const minors: number[] = [];
  for (let v = lo + 10; v < hi; v += 20) minors.push(v);

  // Least-squares fit of actual on predicted, clipped to the plot box. Riding
  // the y=x diagonal means margins are unbiased on average; a flatter slope
  // means the model's confident calls overshoot reality.
  const fit = (() => {
    if (pts.length < 10) return null; // a line through a handful of games is noise
    const n = pts.length;
    const mx = pts.reduce((s, p) => s + p.x, 0) / n;
    const my = pts.reduce((s, p) => s + p.y, 0) / n;
    const sxx = pts.reduce((s, p) => s + (p.x - mx) * (p.x - mx), 0);
    if (sxx === 0) return null;
    const slope = pts.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0) / sxx;
    const icept = my - slope * mx;
    const yAt = (x: number) => icept + slope * x;
    let x1 = lo;
    let x2 = hi;
    if (slope !== 0) {
      const cross = [(lo - icept) / slope, (hi - icept) / slope].sort((a, b) => a - b);
      x1 = Math.max(x1, cross[0]);
      x2 = Math.min(x2, cross[1]);
    }
    if (!(x1 < x2)) return null;
    return [
      { x: x1, y: yAt(x1) },
      { x: x2, y: yAt(x2) },
    ] as const;
  })();

  return (
    <ResponsiveContainer width="100%" height={440}>
      <ScatterChart margin={{ top: 8, right: 20, bottom: 24, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        {/* Wrong-winner quadrants, tinted so the geometry tells the story:
            any point on a tinted field is a missed call. Labels sit in the
            outer corners, where extreme mispredictions are rarest. */}
        <ReferenceArea
          x1={lo}
          x2={0}
          y1={0}
          y2={hi}
          fill="#ef4444"
          fillOpacity={0.07}
          stroke="none"
          label={{
            value: t.marginScatter.quadAwayPick,
            position: "insideTopLeft",
            fill: "#9aa6c0",
            fontSize: 11,
          }}
        />
        <ReferenceArea
          x1={0}
          x2={hi}
          y1={lo}
          y2={0}
          fill="#ef4444"
          fillOpacity={0.07}
          stroke="none"
          label={{
            value: t.marginScatter.quadHomePick,
            position: "insideBottomRight",
            fill: "#9aa6c0",
            fontSize: 11,
          }}
        />
        <XAxis
          type="number"
          dataKey="x"
          domain={[lo, hi]}
          ticks={majors}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{
            value: t.marginScatter.xLabel,
            position: "insideBottom",
            offset: -12,
            fill: "#9aa6c0",
            fontSize: 12,
          }}
        />
        <YAxis
          type="number"
          dataKey="y"
          domain={[lo, hi]}
          ticks={majors}
          width={56}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{
            value: t.marginScatter.yLabel,
            angle: -90,
            position: "insideLeft",
            fill: "#9aa6c0",
            fontSize: 12,
            style: { textAnchor: "middle" },
          }}
        />
        {minors.map((v) => (
          <ReferenceLine key={`mx${v}`} x={v} stroke="#1a2338" />
        ))}
        {minors.map((v) => (
          <ReferenceLine key={`my${v}`} y={v} stroke="#1a2338" />
        ))}
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={(props: unknown) => {
            const { active, payload } = props as {
              active?: boolean;
              payload?: Array<{ payload: Pt }>;
            };
            return <PointTooltip active={active} payload={payload} t={t} />;
          }}
        />
        {/* Legend on top — at the bottom it collided with the x-axis title. */}
        <Legend verticalAlign="top" height={30} />
        <ReferenceLine
          segment={[
            { x: lo, y: lo },
            { x: hi, y: hi },
          ]}
          stroke="#e7ecf5"
          strokeDasharray="5 5"
        />
        <ReferenceLine x={0} stroke="#555" />
        <ReferenceLine y={0} stroke="#555" />
        {/* OLS fit; the caption names it (the only solid orange line here). */}
        {fit && <ReferenceLine segment={fit} stroke="#f97316" strokeWidth={1.5} />}
        <Scatter name={t.marginScatter.winnerCalled} data={hits} fill="#22c55e" fillOpacity={0.55} />
        <Scatter name={t.marginScatter.missed} data={misses} fill="#ef4444" fillOpacity={0.55} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
