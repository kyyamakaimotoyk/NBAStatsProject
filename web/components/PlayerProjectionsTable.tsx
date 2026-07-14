"use client";

import { useMemo, useState } from "react";
import type { PlayerDailyRow } from "@/lib/api";
import { useLang } from "@/lib/i18n";

// The site's first click-to-sort table. Clicking a header sorts by that
// column (second click flips direction); `mode` switches every stat column
// between predicted and actual values (actuals exist once a slate is graded).

type StatKey =
  | "min" | "pts" | "reb" | "ast" | "stl" | "blk"
  | "tov" | "fg3m" | "fg3a" | "ftm" | "fta";

const STAT_COLS: { key: StatKey; label: string }[] = [
  { key: "min", label: "MIN" },
  { key: "pts", label: "PTS" },
  { key: "reb", label: "REB" },
  { key: "ast", label: "AST" },
  { key: "stl", label: "STL" },
  { key: "blk", label: "BLK" },
  { key: "tov", label: "TOV" },
  { key: "fg3m", label: "3PM" },
  { key: "fg3a", label: "3PA" },
  { key: "ftm", label: "FTM" },
  { key: "fta", label: "FTA" },
];

const CTX_COLS: { key: keyof PlayerDailyRow; label: string }[] = [
  { key: "team_pace_l10", label: "Team pace" },
  { key: "opp_pace_l10", label: "Opp pace" },
  { key: "opp_drtg_l10", label: "Opp DRtg" },
  { key: "opp_3pa_allowed_l10", label: "Opp 3PA allowed" },
];

type SortKey = "player" | "matchup" | StatKey | keyof PlayerDailyRow;
export type ValueMode = "pred" | "actual";

function statValue(r: PlayerDailyRow, key: StatKey, mode: ValueMode): number | null {
  return r[`${mode}_${key}` as keyof PlayerDailyRow] as number | null;
}

export default function PlayerProjectionsTable({
  rows,
  mode,
}: {
  rows: PlayerDailyRow[];
  mode: ValueMode;
}) {
  const { t } = useLang();
  const [sortKey, setSortKey] = useState<SortKey>("pts");
  const [dir, setDir] = useState<1 | -1>(-1);

  const isStat = (k: SortKey): k is StatKey =>
    STAT_COLS.some((c) => c.key === (k as string));

  const onSort = (k: SortKey) => {
    if (k === sortKey) {
      setDir(dir === 1 ? -1 : 1);
    } else {
      setSortKey(k);
      setDir(k === "player" || k === "matchup" ? 1 : -1); // text asc, numbers desc
    }
  };

  const sorted = useMemo(() => {
    const val = (r: PlayerDailyRow): string | number | null => {
      if (sortKey === "player") return r.player_name ?? "";
      if (sortKey === "matchup") return `${r.team_abbrev ?? ""}${r.opp_abbrev ?? ""}`;
      if (isStat(sortKey)) return statValue(r, sortKey, mode);
      return r[sortKey as keyof PlayerDailyRow] as number | null;
    };
    return [...rows].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1; // nulls last, either direction
      if (vb == null) return -1;
      if (typeof va === "string" || typeof vb === "string")
        return dir * String(va).localeCompare(String(vb));
      return dir * (Number(va) - Number(vb));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sortKey, dir, mode]);

  const header = (k: SortKey, label: string) => (
    <th
      key={String(k)}
      aria-sort={sortKey === k ? (dir === 1 ? "ascending" : "descending") : undefined}
      className="sortable-th"
    >
      <button type="button" onClick={() => onSort(k)}>
        {label}
        {sortKey === k ? (dir === 1 ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );

  if (rows.length === 0) return <p className="status">{t.playersDaily.noRows}</p>;

  return (
    <div className="results-scroll">
      <table className="pred-table">
        <thead>
          <tr>
            {header("player", t.playersDaily.playerCol)}
            {header("matchup", t.playersDaily.matchupCol)}
            {STAT_COLS.map((c) => header(c.key, c.label))}
            {CTX_COLS.map((c) => header(c.key, t.playersDaily.ctxCols[String(c.key)] ?? c.label))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={`${r.person_id}-${r.game_date}`}>
              <td>{r.player_name ?? r.person_id}</td>
              <td>
                {r.team_abbrev ?? "?"} {r.is_home ? "vs." : "@"} {r.opp_abbrev ?? "?"}
              </td>
              {STAT_COLS.map((c) => {
                const v = statValue(r, c.key, mode);
                return <td key={c.key}>{v != null ? v.toFixed(1) : "—"}</td>;
              })}
              {CTX_COLS.map((c) => {
                const v = r[c.key] as number | null;
                return <td key={String(c.key)}>{v != null ? v : "—"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
