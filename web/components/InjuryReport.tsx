"use client";

import { useEffect, useState } from "react";
import { getInjuryReport, type InjuryItem } from "@/lib/api";

const STATUS_CLASS: Record<string, string> = {
  Out: "inj-out",
  Doubtful: "inj-doubtful",
  Questionable: "inj-questionable",
  Probable: "inj-probable",
  Available: "inj-probable",
};

/** Pre-game injury report for one date, grouped by team. Renders nothing when
 * the date has no report (offseason, or data not yet ingested) — best-effort. */
export default function InjuryReport({ date }: { date: string }) {
  const [injuries, setInjuries] = useState<InjuryItem[] | null>(null);

  useEffect(() => {
    setInjuries(null);
    getInjuryReport(date)
      .then((r) => setInjuries(r.injuries))
      .catch(() => setInjuries([]));
  }, [date]);

  if (!injuries || injuries.length === 0) return null;

  const byTeam = new Map<string, InjuryItem[]>();
  for (const i of injuries) {
    (byTeam.get(i.team_name) ?? byTeam.set(i.team_name, []).get(i.team_name)!).push(i);
  }

  return (
    <>
      <h2>Injury report — {date}</h2>
      <p className="subtle">
        The NBA&apos;s official pre-game injury report for this slate. The models see
        this too — player availability feeds the prediction features.
      </p>
      <div className="injury-grid">
        {[...byTeam.entries()].map(([team, list]) => (
          <div className="injury-team" key={team}>
            <h3>{team}</h3>
            <ul>
              {list.map((i, idx) => (
                <li key={idx}>
                  <span className={`inj-status ${STATUS_CLASS[i.status] ?? ""}`}>
                    {i.status}
                  </span>{" "}
                  {i.player_name}
                  {i.reason && <span className="inj-reason"> — {i.reason}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}
