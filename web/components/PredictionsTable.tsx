"use client";

import { Fragment, useState } from "react";
import type { Prediction } from "@/lib/api";
import { finalScoreLabel } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

// Order of the per-model breakdown: neural net, random forest, XGBoost.
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

/** A margin from one team's side: "+3.1" (wins by), "−1.2" (loses by). Uses a
 * true minus sign; anything that rounds to zero shows as "0.0". */
const signed = (v: number) => {
  const s = Math.abs(v).toFixed(1);
  if (s === "0.0") return s;
  return v > 0 ? `+${s}` : `−${s}`;
};

/** The consensus pick: the team favored by the average of the models'
 * (calibrated) win probabilities. Every other number in the row is then shown
 * from this team's side, so a row only ever names one team. */
function consensus(g: Game) {
  const preds = MODEL_ORDER.map((m) => g.byModel[m]).filter((p): p is Prediction => !!p);
  if (preds.length === 0) return null;
  const avgHome = preds.reduce((s, p) => s + p.home_win_probability, 0) / preds.length;
  const pickHome = avgHome >= 0.5;
  const team = pickHome ? g.home : g.away;
  const side = pickHome ? 1 : -1; // flips home-perspective numbers onto the pick
  const avgMargin = preds.reduce((s, p) => s + p.predicted_margin, 0) / preds.length;
  return {
    team,
    side,
    pct: Math.round((pickHome ? avgHome : 1 - avgHome) * 100),
    margin: side * avgMargin,
    agree: preds.filter((p) => p.predicted_winner === team).length,
    total: preds.length,
    right: g.actualWinner === null ? null : g.actualWinner === team,
  };
}

type Consensus = NonNullable<ReturnType<typeof consensus>>;

/** Tonight's slate: one row per game, four columns. The pick is the team
 * favored by the average of the models' win probabilities; the projected
 * margin and the market line are restated from that team's side so the two
 * are directly comparable. The per-model numbers (each model's win % and
 * margin for the same team) sit in an expandable row underneath. A model
 * whose margin head leans the other way shows a negative margin there. */
export default function PredictionsTable({ predictions }: { predictions: Prediction[] }) {
  const { t } = useLang();
  const games = groupByGame(predictions);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const allOpen = games.length > 0 && games.every((g) => open.has(g.game_id));

  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () =>
    setOpen(allOpen ? new Set() : new Set(games.map((g) => g.game_id)));

  // Matchup + final score live in the sticky first column, and the pick's
  // ✓/✗ sits in the second, so a result is readable without scrolling.
  const matchupCell = (g: Game) => (
    <td className="model-cell matchup-cell">
      {g.away} @ {g.home}
      {g.final && <div className="pick-sub">{g.final}</div>}
    </td>
  );

  const pickCell = (c: Consensus) => (
    <td className="pick" title={t.predTable.pickTitle(c.team, c.pct)}>
      {c.team} <span className="pick-pct">{c.pct}%</span>
      {c.right !== null && (
        <span
          className={`result-mark ${c.right ? "result-win" : "result-loss"}`}
          title={c.right ? t.predTable.pickRight : t.predTable.pickWrong}
        >
          {c.right ? "✓" : "✗"}
        </span>
      )}
      {c.pct <= 55 && <span className="coin-flip">{t.predTable.coinFlip}</span>}
      <div className="pick-sub">{t.predTable.agree(c.agree, c.total)}</div>
    </td>
  );

  const marginCell = (c: Consensus) => (
    <td
      className={`model-cell num-cell${c.margin < 0 ? " against" : ""}`}
      title={t.predTable.marginTitle(c.team, signed(c.margin))}
    >
      {signed(c.margin)}
    </td>
  );

  const marketCell = (g: Game, c: Consensus) => {
    if (g.marketMargin == null) {
      return (
        <td className="model-cell muted" title={t.predTable.noLine}>
          —
        </td>
      );
    }
    if (g.marketMargin === 0) {
      return (
        <td className="model-cell num-cell" title={t.predTable.marketTitle(c.team, "0.0", t.predTable.pickEm)}>
          0.0
          <div className="pick-sub">{t.predTable.pickEm}</div>
        </td>
      );
    }
    const fav = g.marketMargin > 0 ? g.home : g.away;
    const line = `${fav} −${fmt(g.marketMargin)}`;
    const forPick = signed(c.side * g.marketMargin);
    return (
      <td
        className={`model-cell num-cell${c.side * g.marketMargin < 0 ? " against" : ""}`}
        title={t.predTable.marketTitle(c.team, forPick, line)}
      >
        {forPick}
        <div className="pick-sub">{t.predTable.marketLine(line)}</div>
      </td>
    );
  };

  /** The expanded breakdown: each model's win probability and margin, both
   * for the picked team. */
  const detailRow = (g: Game, c: Consensus) => (
    <tr className="model-detail-row" id={`models-${g.game_id}`}>
      <td colSpan={5}>
        <div className="model-detail">
          {MODEL_ORDER.map((m) => {
            const p = g.byModel[m];
            const name = t.models[m] ?? m;
            if (!p) {
              return (
                <div key={m} className="model-detail-item muted">
                  <span className="model-detail-name">{name}</span> —
                </div>
              );
            }
            const pct = Math.round(
              (c.side > 0 ? p.home_win_probability : 1 - p.home_win_probability) * 100,
            );
            const margin = c.side * p.predicted_margin;
            return (
              <div
                key={m}
                className="model-detail-item"
                title={t.predTable.modelTitle(name, c.team, pct, signed(margin))}
              >
                <span className="model-detail-name">{name}</span>{" "}
                <span className={pct < 50 ? "against" : ""}>{pct}%</span>
                <span className="model-detail-sep"> · </span>
                <span className={margin < 0 ? "against" : ""}>{signed(margin)}</span>
              </div>
            );
          })}
        </div>
      </td>
    </tr>
  );

  return (
    <>
      <div className="table-scroll">
        <table className="pred-table slate-table">
          <thead>
            <tr>
              <th className="matchup-cell">{t.predTable.matchup}</th>
              <th>{t.predTable.pick}</th>
              <th title={t.predTable.marginHeaderTitle}>{t.predTable.margin}</th>
              <th title={t.predTable.marketHeaderTitle}>{t.predTable.market}</th>
              <th className="toggle-cell">
                <button
                  type="button"
                  className="row-toggle"
                  onClick={toggleAll}
                  aria-label={allOpen ? t.predTable.hideAll : t.predTable.showAll}
                  title={allOpen ? t.predTable.hideAll : t.predTable.showAll}
                >
                  {allOpen ? "▾" : "▸"}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const c = consensus(g);
              const isOpen = open.has(g.game_id);
              if (!c) {
                return (
                  <tr key={g.game_id}>
                    {matchupCell(g)}
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                    <td />
                  </tr>
                );
              }
              return (
                <Fragment key={g.game_id}>
                  <tr className={isOpen ? "row-open" : undefined}>
                    {matchupCell(g)}
                    {pickCell(c)}
                    {marginCell(c)}
                    {marketCell(g, c)}
                    <td className="toggle-cell">
                      <button
                        type="button"
                        className="row-toggle"
                        onClick={() => toggle(g.game_id)}
                        aria-expanded={isOpen}
                        aria-controls={`models-${g.game_id}`}
                        aria-label={isOpen ? t.predTable.hideModels : t.predTable.showModels}
                        title={isOpen ? t.predTable.hideModels : t.predTable.showModels}
                      >
                        {isOpen ? "▾" : "▸"}
                      </button>
                    </td>
                  </tr>
                  {isOpen && detailRow(g, c)}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="caption">{t.predTable.caption}</p>
    </>
  );
}
