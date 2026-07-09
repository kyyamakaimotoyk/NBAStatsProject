"use client";

import type { TeamContextResponse } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const ROWS: { key: keyof Omit<import("@/lib/api").TeamProfile, "team_id" | "team_abbrev">; label: string }[] = [
  { key: "pace", label: "Pace" },
  { key: "off_rtg", label: "Off. rating" },
  { key: "def_rtg", label: "Def. rating" },
  { key: "efg_pct", label: "eFG%" },
  { key: "oreb_pct", label: "OREB%" },
  { key: "dreb_pct", label: "DREB%" },
  { key: "ast_pct", label: "AST%" },
  { key: "fg3a_pg", label: "3PA / game" },
  { key: "fta_pg", label: "FTA / game" },
  { key: "pts_pg", label: "PTS / game" },
];

// The player's team L10 profile next to the NEXT opponent's — the matchup
// context behind the projections. Offseason: no scheduled game, team only.
export default function TeamComparePanel({ ctx }: { ctx: TeamContextResponse }) {
  const { t } = useLang();
  const opp = ctx.opponent;

  return (
    <>
      {ctx.next_game ? (
        <p className="subtle">
          {t.playersExplore.nextGame(
            ctx.next_game.game_date,
            ctx.next_game.is_home,
            ctx.next_game.opp_abbrev ?? "?",
          )}
        </p>
      ) : (
        <p className="subtle">{t.playersExplore.noNextGame}</p>
      )}
      <table className="pred-table">
        <thead>
          <tr>
            <th>{t.playersExplore.statCol}</th>
            <th>{ctx.team.team_abbrev ?? t.playersExplore.teamCol}</th>
            {opp && <th>{opp.team_abbrev ?? t.playersExplore.oppCol}</th>}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.key}>
              <td>{r.label}</td>
              <td>{ctx.team[r.key] != null ? ctx.team[r.key] : "—"}</td>
              {opp && <td>{opp[r.key] != null ? opp[r.key] : "—"}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="caption">{t.playersExplore.compareCaption}</p>
    </>
  );
}
