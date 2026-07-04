"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { MarginCorrItem } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export default function MarginCorrChart({ items }: { items: MarginCorrItem[] }) {
  const { t } = useLang();
  if (items.length === 0) return <p className="status">{t.drivers.noCorrelations}</p>;

  const maxAbs = Math.max(...items.map((i) => Math.abs(i.correlation)), 0.05);
  const dom = Math.ceil(maxAbs * 110) / 100; // pad ~10%

  return (
    <ResponsiveContainer width="100%" height={Math.max(360, items.length * 26)}>
      <BarChart data={items} layout="vertical" margin={{ top: 8, right: 28, bottom: 22, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243049" />
        <XAxis
          type="number"
          domain={[-dom, dom]}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
          label={{
            value: t.charts.corrXLabel,
            position: "insideBottom",
            offset: -12,
            fill: "#9aa6c0",
            fontSize: 12,
          }}
        />
        <YAxis
          type="category"
          dataKey="feature"
          width={150}
          tick={{ fontSize: 11, fill: "#9aa6c0" }}
        />
        <Tooltip
          contentStyle={{ background: "#141a2e", border: "1px solid #243049" }}
          formatter={(v) => (typeof v === "number" ? v.toFixed(3) : `${v}`)}
        />
        <ReferenceLine x={0} stroke="#555" />
        <Bar dataKey="correlation" isAnimationActive={false}>
          {items.map((i, idx) => (
            <Cell key={idx} fill={i.correlation >= 0 ? "#22c55e" : "#ef4444"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
