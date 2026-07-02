"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { Prediction } from "@/lib/api";

type Pt = {
  x: number; // predicted home-perspective margin
  y: number; // actual home-perspective margin
  date: string;
  home: string;
  away: string;
  pick: string;
  correct: boolean;
};

function PointTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Pt }> }) {
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
        <strong>{p.away}</strong> @ <strong>{p.home}</strong> · picked {p.pick}
      </div>
      <div style={{ marginTop: 4, color: "#9aa6c0" }}>
        predicted {p.x > 0 ? "+" : ""}
        {p.x.toFixed(1)} · actual {p.y > 0 ? "+" : ""}
        {p.y}
      </div>
    </div>
  );
}

export default function MarginScatter({ rows }: { rows: Prediction[] }) {
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
  if (pts.length === 0) return <p className="status">No graded games in this window yet.</p>;

  const hits = pts.filter((p) => p.correct);
  const misses = pts.filter((p) => !p.correct);

  const all = pts.flatMap((p) => [p.x, p.y]);
  const lo = Math.floor(Math.min(...all)) - 2;
  const hi = Math.ceil(Math.max(...all)) + 2;

  return (
    <ResponsiveContainer width="100%" height={420}>
      <ScatterChart margin={{ top: 8, right: 20, bottom: 24, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          type="number"
          dataKey="x"
          domain={[lo, hi]}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{
            value: "Predicted home margin",
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
          width={56}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{
            value: "Actual home margin",
            angle: -90,
            position: "insideLeft",
            fill: "#9aa6c0",
            fontSize: 12,
          }}
        />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={(props: unknown) => {
            const { active, payload } = props as {
              active?: boolean;
              payload?: Array<{ payload: Pt }>;
            };
            return <PointTooltip active={active} payload={payload} />;
          }}
        />
        <Legend />
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
        <Scatter name="Winner called" data={hits} fill="#22c55e" fillOpacity={0.55} />
        <Scatter name="Missed" data={misses} fill="#ef4444" fillOpacity={0.55} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
