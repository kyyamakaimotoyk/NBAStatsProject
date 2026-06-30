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
