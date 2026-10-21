"use client";

import type { Prediction } from "@/lib/api";
import { finalScoreLabel } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

// Column order on the home page: neural net, random forest, XGBoost.
const MODEL_ORDER = ["nn", "rf", "xgb"] as const;

type Game = {
  game_id: string;
  away: string;
  home: string;
  byModel: Partial<Record<string, Prediction>>;
  marketMargin: number | null; // implied home margin; 0 = pick'em
  actualWinner: string | null;
  final: string | null;
};

/** Group the API's one-row-per-(game, model) list into one entry per game,
 * keeping the API's game order. */
function groupByGame(predictions: Prediction[]): Game[] {
  const games = new Map<string, Game>();
  for (const p of predictions) {
    const g =
      games.get(p.game_id) ??
      games
        .set(p.game_id, {
          game_id: p.game_id,
          away: p.away_team,
          home: p.home_team,
          byModel: {},
          marketMargin: null,
          actualWinner: null,
          final: null,
        })
        .get(p.game_id)!;
    g.byModel[p.model_type] = p;
    if (g.marketMargin == null && p.market_margin != null) g.marketMargin = p.market_margin;
    if (g.actualWinner == null) g.actualWinner = p.actual_winner;
    if (g.final == null) g.final = finalScoreLabel(p);
  }
  return [...games.values()];
}

const fmt = (v: number) => Math.abs(v).toFixed(1);

/** Tonight's slate: one row per game. The "models' pick" is the team favored
 * by the AVERAGE of the models' win probabilities, with how many models agree.
 * Each model column shows that model's projected margin, colored once final.
 * The market column is the betting line, a benchmark rather than a pick. */
export default function PredictionsTable({ predictions }: { predictions: Prediction[] }) {
  const { t } = useLang();
  const games = groupByGame(predictions);

  const pickCell = (g: Game) => {
    const preds = MODEL_ORDER.map((m) => g.byModel[m]).filter((p): p is Prediction => !!p);
    if (preds.length === 0) return <td>—</td>;
    const avgHome = preds.reduce((s, p) => s + p.home_win_probability, 0) / preds.length;
    const pickHome = avgHome >= 0.5;
    const team = pickHome ? g.home : g.away;
    const pct = Math.round((pickHome ? avgHome : 1 - avgHome) * 100);
    const agree = preds.filter((p) => p.predicted_winner === team).length;
    return (
      <td className="pick" title={t.predTable.pickTitle(team, pct)}>
        {team} <span className="pick-pct">{pct}%</span>
        {pct <= 55 && <span className="coin-flip">{t.predTable.coinFlip}</span>}
        <div className="pick-sub">{t.predTable.agree(agree, preds.length)}</div>
      </td>
    );
  };

  const modelCell = (m: string, g: Game) => {
    const p = g.byModel[m];
    if (!p) return <td key={m} className="model-cell">—</td>;
    const marginTeam = p.predicted_margin >= 0 ? p.home_team : p.away_team;
    const cls =
      g.actualWinner === null ? "" : marginTeam === g.actualWinner ? "cell-win" : "cell-loss";
    const homePct = Math.round(p.home_win_probability * 100);
    const winPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
    return (
      <td key={m} className={`model-cell ${cls}`} title={t.predTable.modelTitle(p.predicted_winner, winPct)}>
        {t.predTable.modelMargin(marginTeam, fmt(p.predicted_margin))}
      </td>
    );
  };

  const marketCell = (g: Game) => {
    if (g.marketMargin == null) {
      return (
        <td className="model-cell muted" title={t.predTable.noLine}>
          —
        </td>
      );
    }
    if (g.marketMargin === 0) return <td className="model-cell">{t.predTable.pickEm}</td>;
    const fav = g.marketMargin > 0 ? g.home : g.away;
    const line = `${fav} -${fmt(g.marketMargin)}`;
    return (
      <td className="model-cell" title={t.predTable.marketTitle(line)}>
        {line}
      </td>
    );
  };

  const finalCell = (g: Game) => {
    if (!g.final) return <td>—</td>;
    const preds = MODEL_ORDER.map((m) => g.byModel[m]).filter((p): p is Prediction => !!p);
    const avgHome = preds.reduce((s, p) => s + p.home_win_probability, 0) / (preds.length || 1);
    const pick = avgHome >= 0.5 ? g.home : g.away;
    const right = g.actualWinner === null ? null : g.actualWinner === pick;
    return (
      <td className="model-cell">
        {g.final}{" "}
        {right !== null && (
          <span
            className={right ? "result-win" : "result-loss"}
            title={right ? t.predTable.pickRight : t.predTable.pickWrong}
          >
            {right ? "✓" : "✗"}
          </span>
        )}
      </td>
    );
  };

  return (
    <>
      <div className="table-scroll">
        <table className="pred-table slate-table">
          <thead>
            <tr>
              <th>{t.predTable.matchup}</th>
              <th>{t.predTable.pick}</th>
              {MODEL_ORDER.map((m) => (
                <th key={m}>{t.models[m] ?? m}</th>
              ))}
              <th>{t.predTable.market}</th>
              <th>{t.predTable.final}</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => (
              <tr key={g.game_id}>
                <td className="model-cell">
                  {g.away} @ {g.home}
                </td>
                {pickCell(g)}
                {MODEL_ORDER.map((m) => modelCell(m, g))}
                {marketCell(g)}
                {finalCell(g)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">{t.predTable.caption}</p>
    </>
  );
}
