import type { Prediction } from "@/lib/api";
import { MODEL_LABELS } from "@/lib/perf";

export default function ResultsTable({ rows }: { rows: Prediction[] }) {
  // Most recent first; cap for readability.
  const recent = [...rows].sort((a, b) => b.game_date.localeCompare(a.game_date)).slice(0, 60);

  return (
    <table className="pred-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Matchup</th>
          <th>Model</th>
          <th>Pick</th>
          <th>Win prob.</th>
          <th>Proj. margin</th>
          <th>Actual</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        {recent.map((p) => {
          const homePct = Math.round(p.home_win_probability * 100);
          const pickPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
          return (
            <tr key={`${p.game_id}-${p.model_type}`}>
              <td>{p.game_date}</td>
              <td>
                {p.away_team} @ {p.home_team}
              </td>
              <td>{MODEL_LABELS[p.model_type] ?? p.model_type}</td>
              <td className="pick">{p.predicted_winner}</td>
              <td>{pickPct}%</td>
              <td>by {Math.abs(p.predicted_margin).toFixed(1)}</td>
              <td>{p.actual_winner ?? "—"}</td>
              <td>{p.is_correct === null ? "—" : p.is_correct ? "✓" : "✗"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
