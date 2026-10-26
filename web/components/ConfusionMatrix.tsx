"use client";

import type { Confusion } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

/** One model's 2x2 winner-call outcomes. Default: rows = what happened,
 * cols = the pick. `pickRows` transposes it — rows = the pick (home first),
 * cols = what happened — the reading order the track-record page uses. */
export default function ConfusionMatrix({
  label,
  counts,
  pickRows = false,
}: {
  label: string;
  counts: Confusion;
  pickRows?: boolean;
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

  if (pickRows) {
    return (
      <div className="conf-box">
        <div className="conf-title">{label}</div>
        <table className="conf-grid">
          <thead>
            <tr>
              <th />
              <th>{t.confMatrix.homeWon}</th>
              <th>{t.confMatrix.awayWon}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th>{t.confMatrix.pickedHome}</th>
              {cell(counts.tp, true, "TP")}
              {cell(counts.fp, false, "FP")}
            </tr>
            <tr>
              <th>{t.confMatrix.pickedAway}</th>
              {cell(counts.fn, false, "FN")}
              {cell(counts.tn, true, "TN")}
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

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
