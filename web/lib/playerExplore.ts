// Client-side helpers for the player-explore page: window filtering,
// distribution/histogram building, and the Poisson overlay for low-count
// stats. Mirrors perf.ts's role: the API returns raw rows, the browser
// computes everything it charts.

import type { PlayerGameRow } from "@/lib/api";

export type StatKey =
  | "min" | "pts" | "reb" | "ast" | "stl" | "blk"
  | "tov" | "fg3m" | "fg3a" | "ftm" | "fta";

// poisson: low-count stats modeled as Poisson server-side — the distribution
// chart overlays the implied Poisson frequencies for these.
export const STATS: { key: StatKey; label: string; poisson: boolean }[] = [
  { key: "pts", label: "PTS", poisson: false },
  { key: "min", label: "MIN", poisson: false },
  { key: "reb", label: "REB", poisson: false },
  { key: "ast", label: "AST", poisson: false },
  { key: "stl", label: "STL", poisson: true },
  { key: "blk", label: "BLK", poisson: true },
  { key: "tov", label: "TOV", poisson: true },
  { key: "fg3m", label: "3PM", poisson: true },
  { key: "fg3a", label: "3PA", poisson: false },
  { key: "ftm", label: "FTM", poisson: false },
  { key: "fta", label: "FTA", poisson: false },
];

export type WindowKey = "L5" | "L10" | "season" | "three";

// NBA seasons span Oct–Jun: a game in Aug–Dec belongs to the season starting
// that year, Jan–Jul to the season that started the year before.
function seasonStartYear(dateISO: string): number {
  const d = new Date(dateISO);
  return d.getMonth() + 1 >= 8 ? d.getFullYear() : d.getFullYear() - 1;
}

export function windowRows(rows: PlayerGameRow[], win: WindowKey): PlayerGameRow[] {
  if (rows.length === 0) return rows;
  if (win === "L5") return rows.slice(-5);
  if (win === "L10") return rows.slice(-10);
  if (win === "season") {
    const latest = seasonStartYear(rows[rows.length - 1].game_date);
    return rows.filter((r) => seasonStartYear(r.game_date) === latest);
  }
  return rows; // "three": the API already limits to ~3 seasons
}

export const predKey = (k: StatKey) => `pred_${k}` as keyof PlayerGameRow;

export function poissonPmf(lambda: number, k: number): number {
  if (lambda <= 0) return k === 0 ? 1 : 0;
  let logP = -lambda + k * Math.log(lambda);
  for (let i = 2; i <= k; i++) logP -= Math.log(i);
  return Math.exp(logP);
}

export type DistBin = { label: string; share: number; poisson?: number; n: number };

// FIXED per-stat axes so histograms are directly comparable across players:
// Poisson stats get integer bins 0..top (overflow folded into "top+"); the
// rest get fixed-width bins over a fixed range. Never derived from the data.
const INT_TOP: Partial<Record<StatKey, number>> = { stl: 5, blk: 5, tov: 6, fg3m: 8 };
const RANGE: Partial<Record<StatKey, { max: number; step: number }>> = {
  min: { max: 48, step: 4 },
  pts: { max: 50, step: 5 },
  reb: { max: 20, step: 2 },
  ast: { max: 16, step: 2 },
  fg3a: { max: 16, step: 2 },
  ftm: { max: 14, step: 2 },
  fta: { max: 16, step: 2 },
};
// Fixed symmetric range for the error histogram (predicted − actual), per stat.
const ERR_LIM: Record<StatKey, number> = {
  min: 16, pts: 16, reb: 8, ast: 6, stl: 3, blk: 3, tov: 4,
  fg3m: 4, fg3a: 6, ftm: 6, fta: 6,
};

// Empirical distribution of `values` as share-of-games per bin, on the
// stat's FIXED bins. When `lambda` is given (Poisson stats), each integer
// bin also carries the Poisson-implied share for the model-vs-reality overlay.
export function buildDistribution(
  values: number[], key: StatKey, lambda?: number,
): DistBin[] {
  if (values.length === 0) return [];
  const intTop = INT_TOP[key];
  if (intTop !== undefined) {
    const counts = new Array(intTop + 1).fill(0);
    for (const v of values) counts[Math.min(Math.round(v), intTop)] += 1;
    return counts.map((c, k) => ({
      label: k === intTop ? `${k}+` : String(k),
      share: c / values.length,
      n: c,
      ...(lambda !== undefined
        ? { poisson: k === intTop
            ? Math.max(0, 1 - Array.from({ length: intTop }, (_, i) => poissonPmf(lambda, i)).reduce((a, b) => a + b, 0))
            : poissonPmf(lambda, k) }
        : {}),
    }));
  }
  const { max, step } = RANGE[key] ?? { max: 50, step: 5 };
  const nBins = Math.round(max / step);
  const bins: DistBin[] = Array.from({ length: nBins }, (_, i) => ({
    label: String(i * step), // lower edge; short so ticks never collide
    share: 0,
    n: 0,
  }));
  for (const v of values) {
    const i = Math.min(Math.max(Math.floor(v / step), 0), nBins - 1);
    bins[i].share += 1 / values.length;
    bins[i].n += 1;
  }
  return bins;
}

// Signed prediction errors (predicted − actual) over rows that have a
// prediction, on the stat's FIXED symmetric error range (overflow folded
// into the edge bins) — comparable across players and windows.
export function buildErrorDistribution(
  rows: PlayerGameRow[], key: StatKey,
): { bins: DistBin[]; n: number; mae: number | null; bias: number | null } {
  const pk = predKey(key);
  const errs = rows
    .filter((r) => r[pk] != null && r[key] != null)
    .map((r) => Number(r[pk]) - Number(r[key]));
  if (errs.length === 0) return { bins: [], n: 0, mae: null, bias: null };
  const mae = errs.reduce((a, e) => a + Math.abs(e), 0) / errs.length;
  const bias = errs.reduce((a, e) => a + e, 0) / errs.length;
  const lim = ERR_LIM[key];
  const nBins = 8;
  const width = (2 * lim) / nBins;
  const dec = lim <= 4 ? 1 : 0;
  const bins: DistBin[] = Array.from({ length: nBins }, (_, i) => {
    const lo = -lim + i * width;
    return { label: `${lo >= 0 ? "+" : ""}${lo.toFixed(dec)}`, share: 0, n: 0 };
  });
  for (const e of errs) {
    const i = Math.min(Math.max(Math.floor((e + lim) / width), 0), nBins - 1);
    bins[i].share += 1 / errs.length;
    bins[i].n += 1;
  }
  return { bins, n: errs.length, mae, bias };
}
