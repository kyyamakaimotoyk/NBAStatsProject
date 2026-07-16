"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { CurvePoint } from "@/lib/playerExplore";
import { useLang } from "@/lib/i18n";

/**
 * Interactive over-rate curve for the clearing-a-line panel: share of games
 * strictly over each half-point line. A crosshair pins the current line and
 * its over-rate; clicking the plot moves the line to the nearest half point.
 */
export default function ClearCurveChart({
  data,
  line,
  pct,
  statLabel,
  onSelect,
}: {
  data: CurvePoint[];
  line: number;
  pct: number; // exact over-rate at `line` (from clearRate, not interpolated)
  statLabel: string;
  onSelect: (line: number) => void;
}) {
  const { t } = useLang();
  if (data.length === 0) return <p className="status">{t.charts.notEnoughData}</p>;

  const top = data[data.length - 1].x + 0.5;

  return (
    <div className="clear-curve">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart
          data={data}
          margin={{ top: 18, right: 20, bottom: 22, left: 8 }}
          onClick={(state: unknown) => {
            const s = state as { activeLabel?: number | string } | null;
            if (s?.activeLabel != null) onSelect(Number(s.activeLabel));
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
          <XAxis
            dataKey="x"
            type="number"
            domain={[0, top]}
            tickCount={Math.min(11, Math.ceil(top) + 1)}
            tick={{ fontSize: 11, fill: "#9aa6c0" }}
            label={{
              value: `${t.playersExplore.curveXLabel} (${statLabel})`,
              position: "insideBottom",
              offset: -12,
              fill: "#9aa6c0",
              fontSize: 12,
            }}
          />
          <YAxis
            domain={[0, 100]}
            unit="%"
            tick={{ fontSize: 11, fill: "#9aa6c0" }}
            width={48}
            label={{
              value: t.playersExplore.curveYLabel,
              angle: -90,
              position: "insideLeft",
              fill: "#9aa6c0",
              fontSize: 12,
              style: { textAnchor: "middle" },
            }}
          />
          <Tooltip
            contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
            labelFormatter={(x) => t.playersExplore.tileOver(String(x))}
            formatter={(v) => [`${v}%`, t.playersExplore.curveYLabel]}
          />
          {/* Crosshair at the chosen line: read down for the line, across for
              the over-rate. The dot is the intersection the panel reports. */}
          <ReferenceLine x={line} stroke="#f97316" />
          <ReferenceLine y={pct} stroke="#9aa6c0" strokeDasharray="4 4" />
          <Line
            type="linear"
            dataKey="pct"
            name={t.playersExplore.curveYLabel}
            stroke="#3b82f6"
            dot={{ r: 2 }}
            connectNulls
          />
          <ReferenceDot
            x={line}
            y={pct}
            r={5}
            fill="#f97316"
            stroke="#0b1020"
            label={{
              value: `${pct.toFixed(0)}%`,
              position: "top",
              fill: "#f97316",
              fontSize: 12,
              fontWeight: 600,
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
