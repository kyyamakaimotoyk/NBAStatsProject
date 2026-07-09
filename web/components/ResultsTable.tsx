"use client";

import { useState } from "react";
import type { Prediction } from "@/lib/api";
import { finalScoreLabel } from "@/lib/perf";
import { useLang } from "@/lib/i18n";

const MODEL_ORDER = ["rf", "nn", "xgb"] as const;

type GameRow = {
  game_id: string;
  game_date: string;
  away: string;
  home: string;
  final: string | null;
  mm: number | null; // market closing home margin (0 = market makes no call)
  actualWinner: string | null;
  actualMargin: number | null;
  byModel: Partial<Record<string, Prediction>>;
};

type Mode = "su" | "ats";

const fmtNum = (v: number) =>
  Math.abs(v) % 1 ? Math.abs(v).toFixed(1) : String(Math.abs(v));

/** Every game in the window, one row per game, one column per model plus the
 * market, gradable two ways: winner classification (team-only calls), or
 * against the spread — each predictor's OWN line ("SAS -1.7") graded against
 * the final score alone: green if the stated team won by more than its
 * number. The whole table scrolls in place. */
export default function ResultsTable({ rows }: { rows: Prediction[] }) {
  const { t } = useLang();
  const [mode, setMode] = useState<Mode>("su");

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
          mm: null,
          actualWinner: null,
          actualMargin: null,
          byModel: {},
        })
        .get(p.game_id)!;
    g.byModel[p.model_type] = p;
    if (!g.final) g.final = finalScoreLabel(p);
    if (g.mm == null && p.market_margin != null) g.mm = p.market_margin;
    if (g.actualWinner == null) g.actualWinner = p.actual_winner;
    if (g.actualMargin == null) g.actualMargin = p.actual_margin;
  }
  // Newest first.
  const list = [...games.values()].sort(
    (a, b) => b.game_date.localeCompare(a.game_date) || b.game_id.localeCompare(a.game_id),
  );

  // Grade a stated line against the final score: did the favored side win by
  // more than its number? Returns a cell class ("" while ungraded).
  const gradeLine = (favHome: boolean, line: number, actualMargin: number | null) => {
    if (actualMargin === null) return { cls: "", push: false };
    if (actualMargin === line) return { cls: "cell-push", push: true };
    return { cls: actualMargin > line === favHome ? "cell-win" : "cell-loss", push: false };
  };

  const suCell = (m: string, p: Prediction) => {
    const homePct = Math.round(p.home_win_probability * 100);
    const pickPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
    const marginPhrase = t.resultsTable.cellPick(
      p.predicted_margin >= 0 ? p.home_team : p.away_team,
      fmtNum(p.predicted_margin),
    );
    const cls = p.is_correct === null ? "" : p.is_correct ? "cell-win" : "cell-loss";
    return (
      <td
        key={m}
        className={`model-cell ${cls}`}
        title={t.resultsTable.cellTitle(p.predicted_winner, pickPct, pickPct <= 55, marginPhrase)}
      >
        {p.predicted_winner}
      </td>
    );
  };

  // The model's own margin as a sportsbook-style line ("SAS -1.7"), graded
  // against the final score only — the market plays no part in model grading.
  const atsCell = (m: string, p: Prediction) => {
    if (p.predicted_margin === 0)
      return (
        <td key={m} className="model-cell" title={t.resultsTable.noCallTitle}>
          —
        </td>
      );
    const favHome = p.predicted_margin > 0;
    const team = favHome ? p.home_team : p.away_team;
    const num = fmtNum(p.predicted_margin);
    const { cls, push } = gradeLine(favHome, p.predicted_margin, p.actual_margin);
    const title = push ? t.resultsTable.pushTitle : t.resultsTable.cellTitleAts(team, num);
    return (
      <td key={m} className={`model-cell ${cls}`} title={title}>
        {team} -{num}
      </td>
    );
  };

  const cell = (m: string, p: Prediction | undefined) => {
    if (!p) return <td key={m} className="model-cell">—</td>;
    return mode === "su" ? suCell(m, p) : atsCell(m, p);
  };

  // The market's column, graded on the same terms as the models: its favorite
  // in winner mode, its closing line vs the final score in spread mode.
  const marketCell = (g: GameRow) => {
    if (g.mm == null || g.mm === 0) return <td className="model-cell">—</td>;
    const favHome = g.mm > 0;
    const fav = favHome ? g.home : g.away;
    const num = fmtNum(g.mm);
    if (mode === "su") {
      const cls =
        g.actualWinner === null ? "" : fav === g.actualWinner ? "cell-win" : "cell-loss";
      return (
        <td className={`model-cell ${cls}`} title={t.resultsTable.marketTitle(`${fav} -${num}`)}>
          {fav}
        </td>
      );
    }
    const { cls, push } = gradeLine(favHome, g.mm, g.actualMargin);
    const title = push ? t.resultsTable.pushTitle : t.resultsTable.cellTitleAts(fav, num);
    return (
      <td className={`model-cell ${cls}`} title={title}>
        {fav} -{num}
      </td>
    );
  };

  return (
    <>
      <div className="controls table-mode">
        <span>{t.resultsTable.gradeLabel}</span>
        <label className="inline">
          <input type="radio" checked={mode === "su"} onChange={() => setMode("su")} />{" "}
          {t.resultsTable.modeSu}
        </label>
        <label className="inline">
          <input type="radio" checked={mode === "ats"} onChange={() => setMode("ats")} />{" "}
          {t.resultsTable.modeAts}
        </label>
      </div>
      <div className="results-scroll">
        <table className="pred-table results-grid">
          <thead>
            <tr>
              <th>{t.resultsTable.date}</th>
              <th>{t.resultsTable.matchup}</th>
              <th>{t.resultsTable.market}</th>
              <th>{t.resultsTable.final}</th>
              {MODEL_ORDER.map((m) => (
                <th key={m}>{t.models[m] ?? m}</th>
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
                {marketCell(g)}
                <td>{g.final ?? "—"}</td>
                {MODEL_ORDER.map((m) => cell(m, g.byModel[m]))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">
        {mode === "su" ? t.resultsTable.captionSu : t.resultsTable.captionAts}
      </p>
    </>
  );
}
