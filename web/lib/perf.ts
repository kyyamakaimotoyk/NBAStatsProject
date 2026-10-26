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

/**
 * Hit rate by pick confidence: picks bucketed by the probability the model
 * gave its OWN chosen side (max of home/away win prob). Buckets with fewer
 * than MIN_BUCKET_N graded picks emit no bar (a rate over a handful of games
 * is noise); the count always rides along as `<model>_n` for the tooltip.
 */
const MIN_BUCKET_N = 20;
const CONF_BUCKETS = [
  { key: "50–55%", lo: 0.5, hi: 0.55 },
  { key: "55–60%", lo: 0.55, hi: 0.6 },
  { key: "60–65%", lo: 0.6, hi: 0.65 },
  { key: "65%+", lo: 0.65, hi: 1.01 },
];

export function confidenceBuckets(rows: Prediction[]): Pivot {
  const models = [...new Set(rows.map((r) => r.model_type))].sort();
  const acc = new Map<string, Map<string, { c: number; n: number }>>(); // bucket -> model
  for (const r of rows) {
    if (r.is_correct === null) continue;
    const conf = Math.max(r.home_win_probability, 1 - r.home_win_probability);
    const bucket = CONF_BUCKETS.find((b) => conf >= b.lo && conf < b.hi);
    if (!bucket) continue;
    const byModel = acc.get(bucket.key) ?? acc.set(bucket.key, new Map()).get(bucket.key)!;
    const cell =
      byModel.get(r.model_type) ?? byModel.set(r.model_type, { c: 0, n: 0 }).get(r.model_type)!;
    cell.n++;
    if (r.is_correct) cell.c++;
  }
  const data = CONF_BUCKETS.map(({ key }) => {
    const row: Record<string, number | string> = { bucket: key };
    for (const m of models) {
      const cell = acc.get(key)?.get(m);
      row[`${m}_n`] = cell?.n ?? 0;
      if (cell && cell.n >= MIN_BUCKET_N) row[m] = Math.round((cell.c / cell.n) * 1000) / 10;
    }
    return row;
  });
  return { data, models };
}

/**
 * Consensus vs split decisions, over games where all three models logged a
 * graded pick: hit rate when they all agree, the 2-1 majority's rate on split
 * games, and the lone dissenter's rate on those same games.
 */
export function agreementSplit(
  rows: Prediction[],
): { key: "consensus" | "majority" | "dissenter"; pct: number; n: number }[] {
  const byGame = new Map<string, Prediction[]>();
  for (const r of rows) {
    if (r.is_correct === null) continue;
    (byGame.get(r.game_id) ?? byGame.set(r.game_id, []).get(r.game_id)!).push(r);
  }
  const c = { consensus: { c: 0, n: 0 }, majority: { c: 0, n: 0 }, dissenter: { c: 0, n: 0 } };
  for (const rs of byGame.values()) {
    if (rs.length !== 3 || new Set(rs.map((r) => r.model_type)).size !== 3) continue;
    const picks = new Map<string, number>();
    for (const r of rs) picks.set(r.predicted_winner, (picks.get(r.predicted_winner) ?? 0) + 1);
    if (picks.size === 1) {
      c.consensus.n++;
      if (rs[0].is_correct) c.consensus.c++;
    } else {
      const majorityPick = [...picks.entries()].find(([, cnt]) => cnt === 2)?.[0];
      if (majorityPick === undefined) continue; // two teams -> a 3-way split can't happen
      const maj = rs.find((r) => r.predicted_winner === majorityPick)!;
      const dis = rs.find((r) => r.predicted_winner !== majorityPick)!;
      c.majority.n++;
      if (maj.is_correct) c.majority.c++;
      c.dissenter.n++;
      if (dis.is_correct) c.dissenter.c++;
    }
  }
  return (Object.keys(c) as (keyof typeof c)[])
    .filter((k) => c[k].n > 0)
    .map((k) => ({ key: k, pct: Math.round((c[k].c / c[k].n) * 1000) / 10, n: c[k].n }));
}

/**
 * Skill curve: running total of (correct picks - half the games played) per
 * model, plus the market favorite under the `market` key. A coin-flipper
 * drifts along zero. Every series counts ONLY games with a non-zero closing
 * line so the benchmark comparison is same-footing; series are forward-filled
 * so each date carries every line.
 */
export function skillCurve(rows: Prediction[]): Pivot {
  const lined = rows.filter(
    (r) => r.is_correct !== null && r.market_margin != null && r.market_margin !== 0,
  );
  const models = [...new Set(lined.map((r) => r.model_type))].sort();
  // date -> series -> that day's {correct, games}
  const byDate = new Map<string, Map<string, { c: number; n: number }>>();
  const bump = (date: string, series: string, correct: boolean) => {
    const day = byDate.get(date) ?? byDate.set(date, new Map()).get(date)!;
    const cell = day.get(series) ?? day.set(series, { c: 0, n: 0 }).get(series)!;
    cell.n++;
    if (correct) cell.c++;
  };
  const seen = new Set<string>();
  for (const r of lined) {
    bump(r.game_date, r.model_type, r.is_correct === true);
    if (!seen.has(r.game_id)) {
      seen.add(r.game_id);
      bump(r.game_date, "market", (r.market_margin as number) > 0 === homeWon(r));
    }
  }
  const cum = new Map<string, number>([...models, "market"].map((s) => [s, 0]));
  const data = [...byDate.keys()].sort().map((date) => {
    const row: Record<string, number | string> = { date };
    for (const [series, cell] of byDate.get(date)!) {
      cum.set(series, (cum.get(series) ?? 0) + cell.c - 0.5 * cell.n);
    }
    for (const [series, v] of cum) row[series] = Math.round(v * 10) / 10;
    return row;
  });
  return { data, models };
}

export type ErrorHistBin = { x: number; pct: number; n: number };
export type ErrorHist = { model: string; n: number; bins: ErrorHistBin[] };

/**
 * Signed margin-miss distribution per model (predicted - actual home margin),
 * in `binWidth`-point bins centered on multiples of binWidth; everything past
 * +/-clampAt collects in the edge bins. Every model emits the full bin range
 * so the small-multiple panels share one axis.
 */
export function marginErrorHist(rows: Prediction[], binWidth = 5, clampAt = 30): ErrorHist[] {
  const byModel = new Map<string, number[]>();
  for (const r of rows) {
    if (r.actual_margin === null) continue;
    const err = r.predicted_margin - r.actual_margin;
    (byModel.get(r.model_type) ?? byModel.set(r.model_type, []).get(r.model_type)!).push(err);
  }
  const half = clampAt / binWidth;
  const centers = Array.from({ length: 2 * half + 1 }, (_, i) => (i - half) * binWidth);
  return [...byModel.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([model, errs]) => {
      const counts = new Map<number, number>(centers.map((c) => [c, 0]));
      for (const e of errs) {
        const center = Math.max(-half, Math.min(half, Math.round(e / binWidth))) * binWidth;
        counts.set(center, (counts.get(center) ?? 0) + 1);
      }
      return {
        model,
        n: errs.length,
        bins: centers.map((x) => ({
          x,
          n: counts.get(x)!,
          pct: Math.round(((counts.get(x)! / errs.length) * 100) * 10) / 10,
        })),
      };
    });
}

/**
 * Cumulative miss-size distribution: for thresholds 0..maxPts, the share (%) of
 * games whose margin miss |predicted - actual| is within the threshold, per
 * model plus the market closing line under `market`. Every series counts only
 * games with a line (same-footing, like skillCurve); the market is deduped by
 * game so multi-model rows don't triple-count it.
 */
export function missCdf(rows: Prediction[], maxPts = 30, step = 2): Pivot {
  const lined = rows.filter((r) => r.market_margin != null && r.actual_margin !== null);
  if (lined.length === 0) return { data: [], models: [] };
  const models = [...new Set(lined.map((r) => r.model_type))].sort();
  const byModel = new Map<string, number[]>();
  for (const r of lined) {
    (byModel.get(r.model_type) ?? byModel.set(r.model_type, []).get(r.model_type)!).push(
      Math.abs(r.predicted_margin - (r.actual_margin as number)),
    );
  }
  const seen = new Set<string>();
  const marketErrs: number[] = [];
  for (const r of lined) {
    if (seen.has(r.game_id)) continue;
    seen.add(r.game_id);
    marketErrs.push(Math.abs((r.market_margin as number) - (r.actual_margin as number)));
  }
  const within = (errs: number[], x: number) =>
    Math.round((errs.filter((e) => e <= x).length / errs.length) * 1000) / 10;
  const data: Record<string, number | string>[] = [];
  for (let x = 0; x <= maxPts; x += step) {
    const row: Record<string, number | string> = { x };
    for (const m of models) {
      const errs = byModel.get(m)!;
      if (errs.length > 0) row[m] = within(errs, x);
    }
    if (marketErrs.length > 0) row.market = within(marketErrs, x);
    data.push(row);
  }
  return { data, models };
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
    // Market MAE + winner-classification accuracy over the window's distinct
    // games that have a line + a result. The market's "pick" is the favorite
    // (positive implied home margin = home); pick'em lines (0) carry no pick.
    const seen = new Set<string>();
    let mErr = 0;
    let mN = 0;
    let mAccN = 0;
    let mAccC = 0;
    for (const r of win) {
      if (r.market_margin == null || r.actual_margin === null || seen.has(r.game_id)) continue;
      seen.add(r.game_id);
      mErr += Math.abs(r.market_margin - r.actual_margin);
      mN++;
      if (r.market_margin !== 0) {
        mAccN++;
        if (r.market_margin > 0 === homeWon(r)) mAccC++;
      }
    }
    if (mN > 0) row.market_mae = Math.round((mErr / mN) * 10) / 10;
    if (mAccN > 0) row.market_acc = Math.round((mAccC / mAccN) * 1000) / 10;
    return row;
  });
  return { data, models };
}

export type ClassificationRate = { key: string; n: number; pct: number };

/**
 * Winner-classification accuracy for the market and each model, PAIRED on
 * graded games that have a closing line (so all four bars answer the same
 * question on comparable games). The market's pick is the favorite; pick'em
 * lines (implied margin 0) are excluded — the market makes no call there.
 * Returned with the market first (it's the benchmark), then models in fixed
 * order.
 */
export function classificationRates(rows: Prediction[]): ClassificationRate[] {
  const out: ClassificationRate[] = [];

  // Market: distinct games with a non-zero line and a result.
  const seen = new Set<string>();
  let n = 0;
  let c = 0;
  for (const r of rows) {
    if (
      r.market_margin == null || r.market_margin === 0 ||
      r.actual_winner === null || seen.has(r.game_id)
    )
      continue;
    seen.add(r.game_id);
    n++;
    if (r.market_margin > 0 === homeWon(r)) c++;
  }
  if (n > 0) out.push({ key: "market", n, pct: (c / n) * 100 });

  // Models: each judged on its own graded rows within the with-line subset.
  for (const m of [...new Set(rows.map((r) => r.model_type))].sort()) {
    const rs = rows.filter(
      (r) =>
        r.model_type === m && r.is_correct !== null &&
        r.market_margin != null && r.market_margin !== 0,
    );
    if (rs.length > 0)
      out.push({
        key: m,
        n: rs.length,
        pct: (rs.filter((r) => r.is_correct === true).length / rs.length) * 100,
      });
  }
  return out;
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

export type SpreadRecord = { w: number; l: number; ties: number; n: number; pct: number };

/**
 * "Against the spread" record where each prediction is its own line: a win
 * when the team the model's margin favors wins by MORE than that stated
 * margin, a loss otherwise, a tie (excluded from the rate) when the final
 * margin lands exactly on it. Graded against the final score only — the
 * market's number plays no part. A calibrated model's margin is a median
 * estimate, so ~50% is the structural expectation here.
 */
export function spreadRecord(rows: Prediction[]): SpreadRecord | null {
  let w = 0;
  let l = 0;
  let ties = 0;
  for (const r of rows) {
    if (r.actual_margin === null || r.predicted_margin === 0) continue;
    const favHome = r.predicted_margin > 0;
    if (r.actual_margin === r.predicted_margin) ties++;
    else if (r.actual_margin > r.predicted_margin === favHome) w++;
    else l++;
  }
  const n = w + l;
  return n > 0 ? { w, l, ties, n, pct: Math.round((w / n) * 1000) / 10 } : null;
}

export type Confusion = { tp: number; fp: number; fn: number; tn: number };

/**
 * Confusion counts for the market benchmark: one entry per distinct game with
 * a non-zero closing line, the "pick" being the market favorite. Pick'em lines
 * make no call and are excluded (same footing as classificationRates).
 */
export function marketConfusionCounts(rows: Prediction[]): Confusion | null {
  const seen = new Set<string>();
  const c: Confusion = { tp: 0, fp: 0, fn: 0, tn: 0 };
  let n = 0;
  for (const r of rows) {
    if (
      r.market_margin == null ||
      r.market_margin === 0 ||
      r.actual_winner === null ||
      seen.has(r.game_id)
    )
      continue;
    seen.add(r.game_id);
    n++;
    const predHome = r.market_margin > 0;
    const actHome = homeWon(r);
    if (predHome && actHome) c.tp++;
    else if (predHome && !actHome) c.fp++;
    else if (!predHome && actHome) c.fn++;
    else c.tn++;
  }
  return n > 0 ? c : null;
}

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
