// Data-exploration helpers. The feature catalog mirrors the API's allowlist
// (must stay in sync with _EXPLORE_FEATURES in api/queries.py).

import type { FeatureTimeseriesRow } from "./api";

export const FEATURE_CATALOG: { category: string; features: string[] }[] = [
  {
    category: "Traditional",
    features: ["PTS", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA",
      "FT_PCT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS"],
  },
  {
    category: "Advanced",
    features: ["offensiveRating", "defensiveRating", "netRating", "pace", "possessions",
      "EFG_PCT", "TS_PCT", "assistPercentage", "assistToTurnover", "PIE"],
  },
  {
    category: "Four Factors",
    features: ["FT_RATE", "TOV_PCT", "OREB_PCT", "OPP_EFG_PCT", "OPP_FT_RATE", "OPP_TOV_PCT"],
  },
  {
    category: "Hustle",
    features: ["contestedShots", "deflections", "chargesDrawn", "looseBallsRecovered", "boxOuts"],
  },
  {
    category: "Tracking",
    features: ["speed", "distance", "touches", "passes", "secondaryAssists"],
  },
  {
    category: "Misc",
    features: ["pointsOffTurnovers", "pointsSecondChance", "pointsFastBreak", "pointsPaint"],
  },
  {
    category: "Scoring",
    features: ["pctFGA_2pt", "pctFGA_3pt", "pctPTS_2pt", "pctPTS_3pt", "pctAssisted"],
  },
];

// Scatter stats (must stay in sync with _SCATTER_COLUMNS in api/queries.py).
export const SCATTER_CATALOG: { category: string; stats: string[] }[] = [
  {
    category: "Traditional",
    stats: ["PTS", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA",
      "FT_PCT", "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS"],
  },
  {
    category: "Four Factors",
    stats: ["effectiveFieldGoalPercentage", "freeThrowAttemptRate",
      "teamTurnoverPercentage", "offensiveReboundPercentage"],
  },
  { category: "Tracking", stats: ["distance", "touches", "passes", "secondaryAssists"] },
  {
    category: "Hustle",
    stats: ["contestedShots", "deflections", "chargesDrawn", "screenAssists", "boxOuts"],
  },
  { category: "Misc", stats: ["pointsPaint", "pointsSecondChance", "pointsOffTurnovers"] },
  { category: "Scoring", stats: ["percentagePoints3pt", "percentageAssistedFGM"] },
];

/** Ordinary least-squares fit; null if fewer than 2 points or vertical. */
export function linreg(
  pts: { x: number; y: number }[],
): { slope: number; intercept: number } | null {
  const n = pts.length;
  if (n < 2) return null;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (const p of pts) {
    sx += p.x;
    sy += p.y;
    sxx += p.x * p.x;
    sxy += p.x * p.y;
  }
  const d = n * sxx - sx * sx;
  if (d === 0) return null;
  const slope = (n * sxy - sx * sy) / d;
  const intercept = (sy - slope * sx) / n;
  return { slope, intercept };
}

/** Five-number summary (min, quartiles, median, max) for a box plot. */
export type FiveNum = { min: number; q1: number; med: number; q3: number; max: number; n: number };

export function fiveNum(values: number[]): FiveNum | null {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  const n = v.length;
  if (n < 2) return null;
  const q = (p: number) => {
    const idx = p * (n - 1);
    const lo = Math.floor(idx);
    const frac = idx - lo;
    return frac === 0 ? v[lo] : v[lo] + frac * (v[lo + 1] - v[lo]);
  };
  return { min: v[0], q1: q(0.25), med: q(0.5), q3: q(0.75), max: v[n - 1], n };
}

/**
 * Round a data extent outward to a clean step so the scatter axes and the
 * marginal box strips can share the exact same numeric domain.
 */
export function niceDomain(min: number, max: number): [number, number] {
  if (min === max) return [min - 1, max + 1];
  const step = Math.pow(10, Math.floor(Math.log10((max - min) / 4)));
  return [Math.floor(min / step) * step, Math.ceil(max / step) * step];
}

/** Distinct team names present in the response (home or away). */
export function allTeams(rows: FeatureTimeseriesRow[]): string[] {
  const s = new Set<string>();
  for (const r of rows) {
    if (r.home_team) s.add(r.home_team);
    if (r.away_team) s.add(r.away_team);
  }
  return [...s].sort();
}

/**
 * Pivot to one row per date with a column per selected team. For each game a team
 * is in, use the home value if they were home, else the away value.
 */
export function teamSeries(
  rows: FeatureTimeseriesRow[],
  teams: string[],
): { data: Record<string, number | string>[]; teams: string[] } {
  const byDate = new Map<string, Record<string, number | string>>();
  for (const r of rows) {
    for (const team of teams) {
      let v: number | null = null;
      if (r.home_team === team) v = r.home_value;
      else if (r.away_team === team) v = r.away_value;
      if (v === null || v === undefined) continue;
      const row = byDate.get(r.game_date) ?? { date: r.game_date };
      row[team] = Math.round(v * 1000) / 1000;
      byDate.set(r.game_date, row);
    }
  }
  const data = [...byDate.values()].sort((a, b) =>
    String(a.date).localeCompare(String(b.date)),
  );
  return { data, teams };
}
