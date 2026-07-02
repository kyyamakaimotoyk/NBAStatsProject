"use client";

import type { Prediction } from "@/lib/api";

/** The last N graded picks as a green/red strip — the "at a glance" record. */
export default function PicksStrip({ rows, count = 30 }: { rows: Prediction[]; count?: number }) {
  const recent = rows
    .filter((r) => r.is_correct !== null)
    .slice(-count); // rows arrive date-ascending; take the newest, keep chronological order
  if (recent.length === 0) return null;

  return (
    <div className="picks-strip" aria-label={`Last ${recent.length} graded picks`}>
      {recent.map((r) => (
        <span
          key={`${r.game_id}-${r.model_type}`}
          className={`pick-chip ${r.is_correct ? "win" : "loss"}`}
          title={`${r.game_date} — ${r.away_team} @ ${r.home_team}: picked ${r.predicted_winner}, ${
            r.actual_winner
          } won`}
        >
          {r.is_correct ? "✓" : "✗"}
        </span>
      ))}
    </div>
  );
}
