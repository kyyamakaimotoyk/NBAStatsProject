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

// Empirical distribution of `values` as share-of-games per bin. Integer bins
// (0..max) when the stat is small; ~12 equal-width bins otherwise. When
// `lambda` is given (Poisson stats), each integer bin also carries the
// Poisson-implied share so the chart can overlay model vs reality.
export function buildDistribution(values: number[], lambda?: number): DistBin[] {
  if (values.length === 0) return [];
  const max = Math.max(...values);
  if (max <= 12) {
    const top = Math.max(Math.ceil(max), lambda ? Math.ceil(lambda + 3) : 0, 1);
    const counts = new Array(top + 1).fill(0);
    for (const v of values) counts[Math.min(Math.round(v), top)] += 1;
    return counts.map((c, k) => ({
      label: k === top && max > top ? `${k}+` : String(k),
      share: c / values.length,
      n: c,
      ...(lambda !== undefined
        ? { poisson: k === top
            ? Math.max(0, 1 - Array.from({ length: top }, (_, i) => poissonPmf(lambda, i)).reduce((a, b) => a + b, 0))
            : poissonPmf(lambda, k) }
        : {}),
    }));
  }
  const min = Math.min(...values);
  const nBins = 12;
  const width = Math.max((max - min) / nBins, 0.5);
  const bins: DistBin[] = Array.from({ length: nBins }, (_, i) => ({
    label: `${(min + i * width).toFixed(0)}–${(min + (i + 1) * width).toFixed(0)}`,
    share: 0,
    n: 0,
  }));
  for (const v of values) {
    const i = Math.min(Math.floor((v - min) / width), nBins - 1);
    bins[i].share += 1 / values.length;
    bins[i].n += 1;
  }
  return bins;
}

// Signed prediction errors (predicted − actual) over rows that have a
// prediction, binned for the error-distribution chart.
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
  const lim = Math.max(...errs.map(Math.abs), 1);
  const nBins = Math.min(13, Math.max(7, Math.ceil(lim) * 2 + 1));
  const width = (2 * lim) / nBins;
  const bins: DistBin[] = Array.from({ length: nBins }, (_, i) => {
    const lo = -lim + i * width;
    return { label: `${lo >= 0 ? "+" : ""}${lo.toFixed(1)}`, share: 0, n: 0 };
  });
  for (const e of errs) {
    const i = Math.min(Math.floor((e + lim) / width), nBins - 1);
    bins[i].share += 1 / errs.length;
    bins[i].n += 1;
  }
  return { bins, n: errs.length, mae, bias };
}
