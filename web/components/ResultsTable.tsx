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
  byModel: Partial<Record<string, Prediction>>;
};

type Mode = "su" | "ats";

// "+6.5" / "-3" — a side's spread, trailing .0 dropped.
const fmtLine = (v: number) => {
  const abs = Math.abs(v) % 1 ? Math.abs(v).toFixed(1) : String(Math.abs(v));
  return `${v > 0 ? "+" : v < 0 ? "-" : ""}${abs}`;
};

/** Every game in the window, one row per game, one column per model, gradable
 * two ways: straight-up winner calls, or against the market closing line. The
 * whole table scrolls in place (sticky header) rather than being capped. */
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

  const suCell = (m: string, p: Prediction) => {
    const homePct = Math.round(p.home_win_probability * 100);
    const pickPct = p.predicted_winner === p.home_team ? homePct : 100 - homePct;
    const cls = p.is_correct === null ? "" : p.is_correct ? "cell-win" : "cell-loss";
    return (
      <td
        key={m}
        className={`model-cell ${cls}`}
        title={t.resultsTable.cellTitle(p.predicted_winner, pickPct, pickPct <= 55)}
      >
        {t.resultsTable.cellPick(p.predicted_winner, Math.abs(p.predicted_margin).toFixed(1))}
      </td>
    );
  };

  const atsCell = (m: string, p: Prediction) => {
    const mm = p.market_margin;
    // No line, or the model's margin sits exactly on it: no lean to grade.
    if (mm == null || mm === 0 || p.predicted_margin === mm)
      return <td key={m} className="model-cell">—</td>;
    const leanHome = p.predicted_margin > mm;
    const side = leanHome ? p.home_team : p.away_team;
    const sideLine = fmtLine(leanHome ? -mm : mm);
    let cls = "";
    let push = false;
    if (p.actual_margin !== null) {
      if (p.actual_margin === mm) {
        cls = "cell-push";
        push = true;
      } else {
        cls = (p.actual_margin > mm) === leanHome ? "cell-win" : "cell-loss";
      }
    }
    const title = push
      ? t.resultsTable.pushTitle
      : t.resultsTable.cellTitleAts(p.predicted_margin.toFixed(1), fmtLine(mm));
    return (
      <td key={m} className={`model-cell ${cls}`} title={title}>
        {side} {sideLine}
      </td>
    );
  };

  const cell = (m: string, p: Prediction | undefined) => {
    if (!p) return <td key={m} className="model-cell">—</td>;
    return mode === "su" ? suCell(m, p) : atsCell(m, p);
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
