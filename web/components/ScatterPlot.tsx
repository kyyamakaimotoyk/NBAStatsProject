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
import { useLang } from "@/lib/i18n";
import type { Dict } from "@/lib/translations";

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
  t,
}: {
  active?: boolean;
  payload?: Array<{ payload: Pt }>;
  xLabel: string;
  yLabel: string;
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
        <strong>{p.away ?? "?"}</strong> @ <strong>{p.home ?? "?"}</strong>
      </div>
      <div>
        {t.scatter.winnerLabel} <strong>{p.winner ?? "—"}</strong>
      </div>
      <div style={{ marginTop: 4, color: "#9aa6c0" }}>
        {p.team ? `${p.team} · ` : ""}
        {xLabel} {p.x} · {yLabel} {p.y}
      </div>
    </div>
  );
}

/**
 * Fixed plot-area geometry, exported so the marginal box strips can align
 * with the plot area without measuring Recharts internals. plotTop/plotBottom
 * are the y-pixels of the plot area inside the 460px-tall chart:
 * top margin + legend, and height - bottom margin - x-axis.
 */
export const SCATTER_GEOM = {
  height: 460,
  margin: { top: 8, right: 20, bottom: 24, left: 8 },
  yAxisWidth: 56,
  xAxisHeight: 30,
  legendHeight: 30,
  plotLeft: 8 + 56,
  plotRight: 20,
  plotTop: 8 + 30,
  plotBottom: 460 - 24 - 30,
};

export default function ScatterPlot({
  wins,
  losses,
  xLabel,
  yLabel,
  trend,
  xDomain,
  yDomain,
  xTicks,
  yTicks,
}: {
  wins: Pt[];
  losses: Pt[];
  xLabel: string;
  yLabel: string;
  trend: { x1: number; y1: number; x2: number; y2: number } | null;
  xDomain?: [number, number];
  yDomain?: [number, number];
  xTicks?: number[];
  yTicks?: number[];
}) {
  const { t } = useLang();
  if (wins.length + losses.length === 0) return <p className="status">{t.scatter.noPoints}</p>;

  return (
    <ResponsiveContainer width="100%" height={SCATTER_GEOM.height}>
      <ScatterChart margin={SCATTER_GEOM.margin}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          type="number"
          dataKey="x"
          name={xLabel}
          height={SCATTER_GEOM.xAxisHeight}
          domain={xDomain ?? ["auto", "auto"]}
          ticks={xTicks}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{ value: xLabel, position: "insideBottom", offset: -12, fill: "#9aa6c0", fontSize: 12 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name={yLabel}
          width={SCATTER_GEOM.yAxisWidth}
          domain={yDomain ?? ["auto", "auto"]}
          ticks={yTicks}
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
                t={t}
              />
            );
          }}
        />
        {/* Legend on top so it can't collide with the x-axis title. */}
        <Legend verticalAlign="top" height={SCATTER_GEOM.legendHeight} />
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
        <Scatter name={t.scatter.win} data={wins} fill="#22c55e" fillOpacity={0.55} />
        <Scatter name={t.scatter.loss} data={losses} fill="#ef4444" fillOpacity={0.55} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
