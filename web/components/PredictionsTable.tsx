"use client";

import type { Prediction } from "@/lib/api";
import { finalScoreLabel } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

export default function PredictionsTable({
  predictions,
}: {
  predictions: Prediction[];
}) {
  const { t } = useLang();
  return (
    <table className="pred-table">
      <thead>
        <tr>
          <th>{t.predTable.matchup}</th>
          <th>{t.predTable.model}</th>
          <th>{t.predTable.pick}</th>
          <th>{t.predTable.winProb}</th>
          <th>{t.predTable.margin}</th>
          <th>{t.predTable.final}</th>
          <th>{t.predTable.result}</th>
        </tr>
      </thead>
      <tbody>
        {predictions.map((p) => {
          const homePct = Math.round(p.home_win_probability * 100);
          // Probability of the *picked* team winning.
          const pickPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
          const result =
            p.is_correct === null ? "—" : p.is_correct ? "✓" : "✗";
          const rowClass =
            p.is_correct === null ? "" : p.is_correct ? "row-win" : "row-loss";
          const resultClass =
            p.is_correct === null ? "" : p.is_correct ? "result-win" : "result-loss";
          return (
            <tr key={`${p.game_id}-${p.model_type}`} className={rowClass}>
              <td>
                {p.away_team} @ {p.home_team}
              </td>
              <td>{t.models[p.model_type] ?? p.model_type}</td>
              <td className="pick">
                {p.predicted_winner}
                {pickPct <= 55 && <span className="coin-flip">{t.predTable.coinFlip}</span>}
              </td>
              <td>{pickPct}%</td>
              <td>{t.predTable.byMargin(Math.abs(p.predicted_margin).toFixed(1))}</td>
              <td>{finalScoreLabel(p) ?? "—"}</td>
              <td className={resultClass}>{result}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
