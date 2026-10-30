"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Chart primitives for article figures, in the site's chart style (dark panel,
// muted axes, thin marks, straight lines with visible points). Each one is
// wrapped in <Figure>, which supplies the title, caption and data table.

const AXIS = { fontSize: 12, fill: "#9aa6c0" };
const GRID = "#243049";
const TOOLTIP = {
  contentStyle: { background: "#141a2e", border: "1px solid #243049", fontSize: 12 },
  itemStyle: { color: "#e7ecf5" },
  labelStyle: { color: "#e7ecf5" },
  cursor: { fill: "rgba(255,255,255,0.04)" },
};

// Category labels down the side: one line, right-aligned (Recharts' default
// tick wraps well short of the axis width).
function SideTick(props: unknown) {
  const { x, y, payload } = props as { x: number; y: number; payload: { value: string } };
  return (
    <text x={x - 4} y={y} dy={4} textAnchor="end" fontSize={AXIS.fontSize} fill={AXIS.fill}>
      {payload.value}
    </text>
  );
}

const fmt = (v: unknown, decimals: number, unit = "") => `${Number(v).toFixed(decimals)}${unit}`;
// Axis ticks: whole numbers stay whole, fractional ticks (2.5%) keep one decimal.
const tickFmt = (v: number, unit = "") => fmt(v, Number.isInteger(v) ? 0 : 1, unit);
// itemSorter keeps series order (the default sorts by name, which flips Japanese labels).
const LEGEND = { verticalAlign: "top" as const, itemSorter: () => 0, wrapperStyle: { fontSize: 12, color: "#9aa6c0", paddingBottom: 8 } };

type AxisLabel = { value: string; position: "insideBottom" | "insideLeft"; offset?: number; angle?: number };
const xAxisLabel = (value?: string): AxisLabel | undefined =>
  value ? { value, position: "insideBottom", offset: -4 } : undefined;

// --- Range chart: one row per item, a whisker from lo to hi with a dot at the mean.

export type RangeRow = { label: string; mean: number; lo: number; hi: number; color: string };

export function RangeChart({
  rows,
  unit = "",
  decimals = 1,
  domain,
  refLine,
  ticks,
  xLabel,
  labelWidth = 110,
}: {
  rows: RangeRow[];
  unit?: string;
  decimals?: number;
  domain?: [number, number];
  refLine?: number; // reference line, e.g. 0 = "no change"
  ticks?: number[];
  xLabel?: string;
  labelWidth?: number;
}) {
  const data = rows.map((r) => ({ ...r, range: [r.lo, r.hi] }));
  return (
    <ResponsiveContainer width="100%" height={rows.length * 34 + 56}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 20, bottom: 18, left: 4 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={false} />
        <XAxis
          type="number"
          domain={domain ?? ["auto", "auto"]}
          ticks={ticks}
          tick={AXIS}
          tickFormatter={(v) => (v === 0 ? `0${unit}` : `${Number(v.toFixed(decimals))}${unit}`)}
          label={{ ...xAxisLabel(xLabel), fill: "#9aa6c0", fontSize: 12 }}
        />
        <YAxis type="category" dataKey="label" width={labelWidth} tick={SideTick} interval={0} />
        <Tooltip
          {...TOOLTIP}
          formatter={(_v, _n, item) => {
            const p = item?.payload as RangeRow;
            return [
              `${fmt(p.mean, decimals, unit)} (${fmt(p.lo, decimals, unit)} – ${fmt(p.hi, decimals, unit)})`,
              "",
            ];
          }}
        />
        {refLine !== undefined && <ReferenceLine x={refLine} stroke="#9aa6c0" strokeDasharray="4 4" />}
        <Bar
          dataKey="range"
          isAnimationActive={false}
          shape={(props: unknown) => {
            const { x, y, width, height, payload } = props as {
              x: number;
              y: number;
              width: number;
              height: number;
              payload: RangeRow;
            };
            // Bars for [lo, hi] can come back with negative width when lo > hi in
            // screen space; normalise so the whisker always spans lo..hi.
            const left = width >= 0 ? x : x + width;
            const w = Math.abs(width);
            const span = payload.hi - payload.lo;
            const cx = left + (span === 0 ? w / 2 : (w * (payload.mean - payload.lo)) / span);
            const cy = y + height / 2;
            return (
              <g>
                <line x1={left} x2={left + w} y1={cy} y2={cy} stroke={payload.color} strokeWidth={2} />
                <line x1={left} x2={left} y1={cy - 5} y2={cy + 5} stroke={payload.color} strokeWidth={2} />
                <line x1={left + w} x2={left + w} y1={cy - 5} y2={cy + 5} stroke={payload.color} strokeWidth={2} />
                <circle cx={cx} cy={cy} r={5} fill={payload.color} stroke="#0b1020" strokeWidth={2} />
              </g>
            );
          }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

// --- Bars: categories x series, vertical columns or horizontal bars.

export type Series = { key: string; name: string; color: string };

export function Bars({
  data,
  series,
  categoryKey = "label",
  horizontal = false,
  unit = "",
  decimals = 1,
  domain,
  refLine,
  valueLabels = true,
  xLabel,
  yLabel,
  height = 280,
  labelWidth = 110,
  colorKey,
  categoryTicks,
  legend = true,
}: {
  data: Record<string, string | number>[];
  series: Series[];
  categoryKey?: string;
  horizontal?: boolean; // true = bars run left-to-right, categories down the side
  unit?: string;
  decimals?: number;
  domain?: [number, number];
  refLine?: number;
  valueLabels?: boolean;
  xLabel?: string;
  yLabel?: string;
  height?: number;
  labelWidth?: number;
  colorKey?: string; // single series only: per-row color from data[colorKey]
  categoryTicks?: (string | number)[]; // label only these categories (dense histograms)
  legend?: boolean; // false when the figure draws one shared legend (small multiples)
}) {
  const valueAxis = {
    type: "number" as const,
    domain: domain ?? [0, "auto"],
    tick: AXIS,
    tickFormatter: (v: number) => tickFmt(v, unit),
  };
  const categoryAxis = {
    type: "category" as const,
    dataKey: categoryKey,
    tick: AXIS,
    interval: 0,
    ...(categoryTicks ? { ticks: categoryTicks } : {}),
  };
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout={horizontal ? "vertical" : "horizontal"}
        barGap={2}
        margin={{ top: 20, right: horizontal ? 44 : 12, bottom: xLabel ? 18 : 4, left: 4 }}
      >
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis {...valueAxis} label={{ ...xAxisLabel(xLabel), fill: "#9aa6c0", fontSize: 12 }} />
            <YAxis {...categoryAxis} tick={SideTick} width={labelWidth} />
          </>
        ) : (
          <>
            <XAxis {...categoryAxis} label={{ ...xAxisLabel(xLabel), fill: "#9aa6c0", fontSize: 12 }} />
            <YAxis
              {...valueAxis}
              width={yLabel ? 60 : 44}
              label={
                yLabel
                  ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#9aa6c0", fontSize: 12, style: { textAnchor: "middle" } }
                  : undefined
              }
            />
          </>
        )}
        <Tooltip {...TOOLTIP} formatter={(v, name) => [fmt(v, decimals, unit), name]} />
        {legend && series.length > 1 && <Legend {...LEGEND} />}
        {refLine !== undefined &&
          (horizontal ? (
            <ReferenceLine x={refLine} stroke="#9aa6c0" strokeDasharray="4 4" />
          ) : (
            <ReferenceLine y={refLine} stroke="#9aa6c0" strokeDasharray="4 4" />
          ))}
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            fill={s.color}
            fillOpacity={0.9}
            isAnimationActive={false}
            radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            maxBarSize={horizontal ? 22 : 44}
          >
            {colorKey && data.map((d, i) => <Cell key={i} fill={String(d[colorKey])} />)}
            {valueLabels && (
              <LabelList
                dataKey={s.key}
                position={horizontal ? "right" : "top"}
                formatter={(v: unknown) => fmt(v, decimals, unit)}
                fill="#e7ecf5"
                fontSize={11}
              />
            )}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// --- Lines: numeric x, one or more series; straight segments with visible points.

export function Lines({
  data,
  series,
  xKey = "x",
  unit = "",
  xUnit = "",
  decimals = 1,
  xLabel,
  yLabel,
  refX,
  xTicks,
  height = 280,
}: {
  data: Record<string, number>[];
  series: Series[];
  xKey?: string;
  unit?: string;
  xUnit?: string;
  decimals?: number;
  xLabel?: string;
  yLabel?: string;
  refX?: number;
  xTicks?: number[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: xLabel ? 18 : 4, left: 4 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
        <XAxis
          dataKey={xKey}
          type="number"
          domain={["dataMin", "dataMax"]}
          ticks={xTicks}
          tick={AXIS}
          tickFormatter={(v) => `${v}${xUnit}`}
          label={{ ...xAxisLabel(xLabel), fill: "#9aa6c0", fontSize: 12 }}
        />
        <YAxis
          domain={[0, 100]}
          width={yLabel ? 60 : 44}
          tick={AXIS}
          tickFormatter={(v) => `${v}${unit}`}
          label={
            yLabel
              ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#9aa6c0", fontSize: 12, style: { textAnchor: "middle" } }
              : undefined
          }
        />
        <Tooltip
          {...TOOLTIP}
          labelFormatter={(x) => `${x}${xUnit}`}
          formatter={(v, name) => [fmt(v, decimals, unit), name]}
        />
        {series.length > 1 && <Legend {...LEGEND} />}
        {refX !== undefined && <ReferenceLine x={refX} stroke="#9aa6c0" strokeDasharray="4 4" />}
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            name={s.name}
            type="linear"
            stroke={s.color}
            strokeWidth={2}
            dot={{ r: 3, fill: s.color, strokeWidth: 0 }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
