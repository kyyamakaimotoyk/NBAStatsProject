import type { Prediction } from "@/lib/api";

const MODEL_LABELS: Record<string, string> = {
  rf: "Random Forest",
  nn: "Neural Net",
  xgb: "XGBoost",
};

export default function PredictionsTable({
  predictions,
}: {
  predictions: Prediction[];
}) {
  return (
    <table className="pred-table">
      <thead>
        <tr>
          <th>Matchup</th>
          <th>Model</th>
          <th>Pick</th>
          <th>Win prob.</th>
          <th>Margin</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        {predictions.map((p) => {
          const homePct = Math.round(p.home_win_probability * 100);
          // Probability of the *picked* team winning.
          const pickPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
          const result =
            p.is_correct === null ? "—" : p.is_correct ? "✓" : "✗";
          return (
            <tr key={`${p.game_id}-${p.model_type}`}>
              <td>
                {p.away_team} @ {p.home_team}
              </td>
              <td>{MODEL_LABELS[p.model_type] ?? p.model_type}</td>
              <td className="pick">{p.predicted_winner}</td>
              <td>{pickPct}%</td>
              <td>by {Math.abs(p.predicted_margin).toFixed(1)}</td>
              <td>{result}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
