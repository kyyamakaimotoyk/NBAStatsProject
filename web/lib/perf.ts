// Pure client-side aggregations over predicted-vs-actual rows. The API returns raw
// rows; the browser computes every metric/chart here (web tier never computes).

import type { Prediction } from "./api";

// Model display names live in lib/translations.ts (t.models) so they localize.

const homeWon = (p: Prediction) => p.actual_winner === p.home_team;

/** "NYK 125–119" once the game is final; null before that. */
export function finalScoreLabel(p: Prediction): string | null {
  if (p.home_score == null || p.away_score == null) return null;
  const winner = p.home_score > p.away_score ? p.home_team : p.away_team;
  const hi = Math.max(p.home_score, p.away_score);
  const lo = Math.min(p.home_score, p.away_score);
  return `${winner} ${hi}–${lo}`;
}

export type ModelSummary = {
  model: string;
  n: number;
  accuracyPct: number;
  mae: number;
  calibrationErr: number;
};

/** Per-model headline metrics: accuracy, mean absolute margin error, calibration error. */
export function summaryByModel(rows: Prediction[]): ModelSummary[] {
  const byModel = new Map<string, Prediction[]>();
  for (const r of rows) {
    (byModel.get(r.model_type) ?? byModel.set(r.model_type, []).get(r.model_type)!).push(r);
  }
  const out: ModelSummary[] = [];
  for (const [model, rs] of byModel) {
    const n = rs.length;
    const correct = rs.filter((r) => r.is_correct === true).length;
    const withMargin = rs.filter((r) => r.actual_margin !== null);
    const mae =
      withMargin.length === 0
        ? 0
        : withMargin.reduce(
            (s, r) => s + Math.abs(r.predicted_margin - (r.actual_margin as number)),
            0,
          ) / withMargin.length;
    const calib =
      rs.reduce((s, r) => s + Math.abs(r.home_win_probability - (homeWon(r) ? 1 : 0)), 0) / n;
    out.push({ model, n, accuracyPct: (correct / n) * 100, mae, calibrationErr: calib });
  }
  return out.sort((a, b) => a.model.localeCompare(b.model));
}

type Pivot = { data: Record<string, number | string>[]; models: string[] };

/** One row per game_date with each model's hit-rate (%) that day. */
export function dailyAccuracy(rows: Prediction[]): Pivot {
  const byDate = new Map<string, Map<string, { c: number; n: number }>>();
  const models = new Set<string>();
  for (const r of rows) {
    models.add(r.model_type);
    const day = byDate.get(r.game_date) ?? byDate.set(r.game_date, new Map()).get(r.game_date)!;
    const cell = day.get(r.model_type) ?? day.set(r.model_type, { c: 0, n: 0 }).get(r.model_type)!;
    cell.n++;
    if (r.is_correct === true) cell.c++;
  }
  const data = [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, m]) => {
      const row: Record<string, number | string> = { date };
      for (const [model, cell] of m) row[model] = Math.round((cell.c / cell.n) * 100);
      return row;
    });
  return { data, models: [...models].sort() };
}

const dayNum = (iso: string) => Math.floor(Date.parse(`${iso}T00:00:00Z`) / 86_400_000);

export type TrendRow = Record<string, number | string>;

/**
 * Trailing-window trend per game date: for each date, look back `windowDays` and
 * compute each model's winner accuracy (%) and margin MAE, plus the market closing
 * line's MAE over the same games (deduped by game so multi-model rows don't
 * double-count). Keys: `<model>_acc`, `<model>_mae`, `market_mae`.
 */
export function trendSeries(
  rows: Prediction[],
  windowDays = 7,
): { data: TrendRow[]; models: string[] } {
  const graded = rows.filter((r) => r.is_correct !== null);
  const models = [...new Set(graded.map((r) => r.model_type))].sort();
  const dates = [...new Set(graded.map((r) => r.game_date))].sort();

  const data = dates.map((d) => {
    const end = dayNum(d);
    const win = graded.filter((r) => {
      const t = dayNum(r.game_date);
      return t <= end && t > end - windowDays;
    });
    const row: TrendRow = { date: d };
    for (const m of models) {
      const rs = win.filter((r) => r.model_type === m);
      if (rs.length === 0) continue;
      row[`${m}_acc`] = Math.round(
        (rs.filter((r) => r.is_correct === true).length / rs.length) * 1000,
      ) / 10;
      const withMargin = rs.filter((r) => r.actual_margin !== null);
      if (withMargin.length > 0) {
        row[`${m}_mae`] =
          Math.round(
            (withMargin.reduce(
              (s, r) => s + Math.abs(r.predicted_margin - (r.actual_margin as number)),
              0,
            ) / withMargin.length) * 10,
          ) / 10;
      }
    }
    // Market MAE over the window's distinct games that have a line + a result.
    const seen = new Set<string>();
    let mErr = 0;
    let mN = 0;
    for (const r of win) {
      if (r.market_margin == null || r.actual_margin === null || seen.has(r.game_id)) continue;
      seen.add(r.game_id);
      mErr += Math.abs(r.market_margin - r.actual_margin);
      mN++;
    }
    if (mN > 0) row.market_mae = Math.round((mErr / mN) * 10) / 10;
    return row;
  });
  return { data, models };
}

export type HomeAwaySplit = {
  home: { n: number; pct: number };
  away: { n: number; pct: number };
};

/** How often the model is right when it picks the home team vs the away team. */
export function homeAwaySplit(rows: Prediction[]): HomeAwaySplit | null {
  const graded = rows.filter((r) => r.is_correct !== null);
  const home = graded.filter((r) => r.predicted_winner === r.home_team);
  const away = graded.filter((r) => r.predicted_winner !== r.home_team);
  if (home.length === 0 && away.length === 0) return null;
  const pct = (rs: Prediction[]) =>
    rs.length === 0 ? 0 : Math.round((rs.filter((r) => r.is_correct === true).length / rs.length) * 100);
  return {
    home: { n: home.length, pct: pct(home) },
    away: { n: away.length, pct: pct(away) },
  };
}

export type MarketCompare = {
  n: number; // games with both a market line and a result
  modelMae: number;
  marketMae: number;
  closerPct: number; // % of those games where the model was nearer the final margin
};

/** Model vs the market closing line, over the games where both exist. */
export function marketCompare(modelRows: Prediction[]): MarketCompare | null {
  const both = modelRows.filter(
    (r) => r.market_margin != null && r.actual_margin !== null,
  );
  if (both.length === 0) return null;
  let modelErr = 0;
  let marketErr = 0;
  let closer = 0;
  for (const r of both) {
    const me = Math.abs(r.predicted_margin - (r.actual_margin as number));
    const ve = Math.abs((r.market_margin as number) - (r.actual_margin as number));
    modelErr += me;
    marketErr += ve;
    if (me < ve) closer++;
  }
  return {
    n: both.length,
    modelMae: modelErr / both.length,
    marketMae: marketErr / both.length,
    closerPct: Math.round((closer / both.length) * 100),
  };
}

export type RocPoint = { fpr: number; tpr: number };

/**
 * ROC for "home team wins" as the positive class, swept over the model's predicted
 * home-win probability. Returns points in % (0-100) plus the AUC. Null when the
 * window lacks both a home win and a home loss (curve undefined).
 */
export function rocCurve(rows: Prediction[]): { points: RocPoint[]; auc: number } | null {
  const graded = rows
    .filter((r) => r.actual_winner !== null)
    .map((r) => ({ p: r.home_win_probability, pos: homeWon(r) }))
    .sort((a, b) => b.p - a.p);
  const P = graded.filter((g) => g.pos).length;
  const N = graded.length - P;
  if (P === 0 || N === 0) return null;

  const points: RocPoint[] = [{ fpr: 0, tpr: 0 }];
  let tp = 0;
  let fp = 0;
  let auc = 0;
  let prevFpr = 0;
  let prevTpr = 0;
  for (let i = 0; i < graded.length; i++) {
    if (graded[i].pos) tp++;
    else fp++;
    // Emit a point only when the threshold actually moves (ties stay grouped).
    if (i + 1 < graded.length && graded[i + 1].p === graded[i].p) continue;
    const fpr = fp / N;
    const tpr = tp / P;
    auc += ((fpr - prevFpr) * (tpr + prevTpr)) / 2; // trapezoid
    prevFpr = fpr;
    prevTpr = tpr;
    points.push({ fpr: Math.round(fpr * 1000) / 10, tpr: Math.round(tpr * 1000) / 10 });
  }
  return { points, auc };
}

export type Confusion = { tp: number; fp: number; fn: number; tn: number };

/** 2x2 winner-call outcomes: predicted home/away pick vs the actual winner. */
export function confusionCounts(rows: Prediction[]): Confusion | null {
  const graded = rows.filter((r) => r.actual_winner !== null);
  if (graded.length === 0) return null;
  const c: Confusion = { tp: 0, fp: 0, fn: 0, tn: 0 };
  for (const r of graded) {
    const predHome = r.predicted_winner === r.home_team;
    const actHome = homeWon(r);
    if (predHome && actHome) c.tp++;
    else if (predHome && !actHome) c.fp++;
    else if (!predHome && actHome) c.fn++;
    else c.tn++;
  }
  return c;
}

/**
 * Reliability/calibration: bin the predicted home-win probability into deciles; for
 * each bin, the observed fraction of home wins (%). A well-calibrated model tracks the
 * y=x diagonal.
 */
export function calibrationBins(rows: Prediction[]): Pivot {
  const models = new Set<string>();
  const acc = new Map<string, Map<number, { h: number; n: number }>>();
  for (const r of rows) {
    models.add(r.model_type);
    const bin = Math.min(9, Math.max(0, Math.floor(r.home_win_probability * 10)));
    const m = acc.get(r.model_type) ?? acc.set(r.model_type, new Map()).get(r.model_type)!;
    const cell = m.get(bin) ?? m.set(bin, { h: 0, n: 0 }).get(bin)!;
    cell.n++;
    if (homeWon(r)) cell.h++;
  }
  const data: Record<string, number | string>[] = [];
  for (let bin = 0; bin < 10; bin++) {
    const row: Record<string, number | string> = { x: bin * 10 + 5 };
    for (const model of models) {
      const cell = acc.get(model)?.get(bin);
      if (cell && cell.n > 0) row[model] = Math.round((cell.h / cell.n) * 100);
    }
    data.push(row);
  }
  return { data, models: [...models].sort() };
}
