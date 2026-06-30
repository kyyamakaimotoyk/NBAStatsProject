// Pure client-side aggregations over predicted-vs-actual rows. The API returns raw
// rows; the browser computes every metric/chart here (web tier never computes).

import type { Prediction } from "./api";

export const MODEL_LABELS: Record<string, string> = {
  rf: "Random Forest",
  nn: "Neural Net",
  xgb: "XGBoost",
};

const homeWon = (p: Prediction) => p.actual_winner === p.home_team;

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
