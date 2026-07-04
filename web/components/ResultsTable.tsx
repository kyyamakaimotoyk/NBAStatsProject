import type { Prediction } from "@/lib/api";
import { finalScoreLabel } from "@/lib/perf";

const MODEL_ORDER = ["rf", "nn", "xgb"] as const;
const MODEL_HEADERS: Record<string, string> = {
  rf: "Random Forest",
  nn: "Neural Net",
  xgb: "XGBoost",
};

type GameRow = {
  game_id: string;
  game_date: string;
  away: string;
  home: string;
  final: string | null;
  byModel: Partial<Record<string, Prediction>>;
};

/** Every game in the window, one row per game, one column per model. The whole
 * table scrolls in place (sticky header) rather than being capped. */
export default function ResultsTable({ rows }: { rows: Prediction[] }) {
  const games = new Map<string, GameRow>();
  for (const p of rows) {
    const g =
      games.get(p.game_id) ??
      games
        .set(p.game_id, {
          game_id: p.game_id,
          game_date: p.game_date,
          away: p.away_team,
          home: p.home_team,
          final: finalScoreLabel(p),
          byModel: {},
        })
        .get(p.game_id)!;
    g.byModel[p.model_type] = p;
    if (!g.final) g.final = finalScoreLabel(p);
  }
  // Newest first.
  const list = [...games.values()].sort(
    (a, b) => b.game_date.localeCompare(a.game_date) || b.game_id.localeCompare(a.game_id),
  );

  const cell = (m: string, p: Prediction | undefined) => {
    if (!p) return <td key={m} className="model-cell">—</td>;
    const homePct = Math.round(p.home_win_probability * 100);
    const pickPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
    const cls =
      p.is_correct === null ? "" : p.is_correct ? "cell-win" : "cell-loss";
    return (
      <td
        key={m}
        className={`model-cell ${cls}`}
        title={`${p.predicted_winner} at ${pickPct}% win probability${
          pickPct <= 55 ? " (coin flip)" : ""
        }`}
      >
        {p.predicted_winner} by {Math.abs(p.predicted_margin).toFixed(1)}
      </td>
    );
  };

  return (
    <div className="results-scroll">
      <table className="pred-table results-grid">
        <thead>
          <tr>
            <th>Date</th>
            <th>Matchup</th>
            <th>Final</th>
            {MODEL_ORDER.map((m) => (
              <th key={m}>{MODEL_HEADERS[m]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((g) => (
            <tr key={g.game_id}>
              <td>{g.game_date}</td>
              <td>
                {g.away} @ {g.home}
              </td>
              <td>{g.final ?? "—"}</td>
              {MODEL_ORDER.map((m) => cell(m, g.byModel[m]))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
