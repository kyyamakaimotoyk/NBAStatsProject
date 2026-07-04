"use client";

import type { Confusion } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

/** One model's 2x2 winner-call outcomes. Rows = what happened, cols = the pick. */
export default function ConfusionMatrix({
  label,
  counts,
}: {
  label: string;
  counts: Confusion;
}) {
  const { t } = useLang();
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
            <th>{t.confMatrix.pickedAway}</th>
            <th>{t.confMatrix.pickedHome}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>{t.confMatrix.awayWon}</th>
            {cell(counts.tn, true, "TN")}
            {cell(counts.fp, false, "FP")}
          </tr>
          <tr>
            <th>{t.confMatrix.homeWon}</th>
            {cell(counts.fn, false, "FN")}
            {cell(counts.tp, true, "TP")}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
