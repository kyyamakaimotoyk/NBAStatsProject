"use client";

import type { Confusion } from "@/lib/perf";

/** One model's 2x2 winner-call outcomes. Rows = what happened, cols = the pick. */
export default function ConfusionMatrix({
  label,
  counts,
}: {
  label: string;
  counts: Confusion;
}) {
  const total = counts.tp + counts.fp + counts.fn + counts.tn;
  if (total === 0) return null;
  const pct = (n: number) => `${Math.round((n / total) * 100)}%`;

  const cell = (n: number, good: boolean, tag: string) => (
    <td className={`conf-cell ${good ? "good" : "bad"}`}>
      <div className="conf-n">{n}</div>
      <div className="conf-sub">
        {tag} · {pct(n)}
      </div>
    </td>
  );

  return (
    <div className="conf-box">
      <div className="conf-title">{label}</div>
      <table className="conf-grid">
        <thead>
          <tr>
            <th />
            <th>Picked away</th>
            <th>Picked home</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Away won</th>
            {cell(counts.tn, true, "TN")}
            {cell(counts.fp, false, "FP")}
          </tr>
          <tr>
            <th>Home won</th>
            {cell(counts.fn, false, "FN")}
            {cell(counts.tp, true, "TP")}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
