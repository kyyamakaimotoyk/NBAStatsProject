"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  getPlayerDaily,
  getPlayerDailyLatest,
  type PlayerDailyResponse,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";
import PlayerProjectionsTable, { type ValueMode } from "@/components/PlayerProjectionsTable";
import PageGuide from "@/components/PageGuide";

export default function PlayersContent({
  initialData,
}: {
  // Latest slate baked at build time by page.tsx (null if the API was down).
  initialData: PlayerDailyResponse | null;
}) {
  const { t } = useLang();
  const [date, setDate] = useState<string | null>(null); // null = latest
  const [data, setData] = useState<PlayerDailyResponse | null>(initialData);
  const [team, setTeam] = useState<string>("all");
  const [mode, setMode] = useState<ValueMode>("pred");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // On mount (date === null) keep the baked slate on screen while it refreshes;
    // only a user-picked date blanks the table.
    if (date !== null) setData(null);
    setError(null);
    (date ? getPlayerDaily(date) : getPlayerDailyLatest())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [date]);

  const teams = useMemo(() => {
    const s = new Set<string>();
    for (const r of data?.rows ?? []) if (r.team_abbrev) s.add(r.team_abbrev);
    return [...s].sort();
  }, [data]);

  const rows = useMemo(
    () => (data?.rows ?? []).filter((r) => team === "all" || r.team_abbrev === team),
    [data, team],
  );

  const graded = useMemo(() => rows.some((r) => r.actual_pts != null), [rows]);

  return (
    <section>
      <h1>{t.playersDaily.title}</h1>
      <p className="subtle">
        {t.playersDaily.subtitle}{" "}
        <Link href="/players/explore">{t.playersDaily.exploreLink}</Link>
      </p>

      <div className="controls explore-controls">
        <label>
          {t.playersDaily.dateLabel}{" "}
          <input
            type="date"
            value={date ?? data?.game_date ?? ""}
            onChange={(e) => setDate(e.target.value || null)}
          />
        </label>
        <label>
          {t.playersDaily.teamLabel}{" "}
          <select value={team} onChange={(e) => setTeam(e.target.value)}>
            <option value="all">{t.playersDaily.allTeams}</option>
            {teams.map((tm) => (
              <option key={tm} value={tm}>
                {tm}
              </option>
            ))}
          </select>
        </label>
        {graded && (
          <div role="radiogroup" aria-label={t.playersDaily.modeLabel}>
            {(["pred", "actual"] as ValueMode[]).map((m) => (
              <label key={m}>
                <input
                  type="radio"
                  name="value-mode"
                  checked={mode === m}
                  onChange={() => setMode(m)}
                />{" "}
                {m === "pred" ? t.playersDaily.modePred : t.playersDaily.modeActual}
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <p className="status error">{t.playersDaily.errLoad(error)}</p>}
      {!error && !data && <p className="status">{t.playersDaily.loading}</p>}
      {!error && data && data.game_date == null && (
        <p className="status">{t.playersDaily.noData}</p>
      )}
      {!error && data && data.game_date != null && (
        <>
          <h2>{t.playersDaily.tableHeading(data.game_date, rows.length)}</h2>
          <PlayerProjectionsTable rows={rows} mode={graded ? mode : "pred"} />
          <p className="caption">
            {graded ? t.playersDaily.gradedNote : t.playersDaily.upcomingNote}{" "}
            {t.playersDaily.contextNote}
          </p>
        </>
      )}
      <PageGuide page="players" />
    </section>
  );
}
