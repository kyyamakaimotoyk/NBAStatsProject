"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

type Pt = {
  x: number;
  y: number;
  team: string | null;
  date: string;
  home: string | null;
  away: string | null;
  winner: string | null;
};

function PointTooltip({
  active,
  payload,
  xLabel,
  yLabel,
}: {
  active?: boolean;
  payload?: Array<{ payload: Pt }>;
  xLabel: string;
  yLabel: string;
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
        <strong>{p.away ?? "?"}</strong> @ <strong>{p.home ?? "?"}</strong>
      </div>
      <div>
        Winner: <strong>{p.winner ?? "—"}</strong>
      </div>
      <div style={{ marginTop: 4, color: "#9aa6c0" }}>
        {p.team ? `${p.team} · ` : ""}
        {xLabel} {p.x} · {yLabel} {p.y}
      </div>
    </div>
  );
}

export default function ScatterPlot({
  wins,
  losses,
  xLabel,
  yLabel,
  trend,
}: {
  wins: Pt[];
  losses: Pt[];
  xLabel: string;
  yLabel: string;
  trend: { x1: number; y1: number; x2: number; y2: number } | null;
}) {
  if (wins.length + losses.length === 0) return <p className="status">No points.</p>;

  return (
    <ResponsiveContainer width="100%" height={460}>
      <ScatterChart margin={{ top: 8, right: 20, bottom: 24, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          type="number"
          dataKey="x"
          name={xLabel}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{ value: xLabel, position: "insideBottom", offset: -12, fill: "#9aa6c0", fontSize: 12 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name={yLabel}
          width={56}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: "#9aa6c0", fontSize: 12 }}
        />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={(props: unknown) => {
            const { active, payload } = props as {
              active?: boolean;
              payload?: Array<{ payload: Pt }>;
            };
            return (
              <PointTooltip
                active={active}
                payload={payload}
                xLabel={xLabel}
                yLabel={yLabel}
              />
            );
          }}
        />
        {/* Legend on top so it can't collide with the x-axis title. */}
        <Legend verticalAlign="top" height={30} />
        {trend && (
          <ReferenceLine
            segment={[
              { x: trend.x1, y: trend.y1 },
              { x: trend.x2, y: trend.y2 },
            ]}
            stroke="#e7ecf5"
            strokeDasharray="5 5"
            ifOverflow="extendDomain"
          />
        )}
        <Scatter name="Win" data={wins} fill="#22c55e" fillOpacity={0.55} />
        <Scatter name="Loss" data={losses} fill="#ef4444" fillOpacity={0.55} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
