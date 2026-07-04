"use client";

import { useState } from "react";
import type { Prediction } from "@/lib/api";
import { finalScoreLabel } from "@/lib/perf";

/** The last N graded picks as a green/red strip — the "at a glance" record.
 * Tap/click a square to see the game below (hover-only tooltips are dead on
 * touch screens, so the detail line is the mobile-first affordance). */
export default function PicksStrip({ rows, count = 30 }: { rows: Prediction[]; count?: number }) {
  const [selected, setSelected] = useState<Prediction | null>(null);
  const recent = rows
    .filter((r) => r.is_correct !== null)
    .slice(-count); // rows arrive date-ascending; take the newest, keep chronological order
  if (recent.length === 0) return null;

  return (
    <>
      <div className="picks-strip" aria-label={`Last ${recent.length} graded picks`}>
        {recent.map((r) => {
          const key = `${r.game_id}-${r.model_type}`;
          const isSel =
            selected !== null &&
            selected.game_id === r.game_id &&
            selected.model_type === r.model_type;
          return (
            <button
              key={key}
              type="button"
              className={`pick-chip ${r.is_correct ? "win" : "loss"}${isSel ? " selected" : ""}`}
              aria-pressed={isSel}
              onClick={() => setSelected(isSel ? null : r)}
              title={`${r.game_date} — ${r.away_team} @ ${r.home_team}: picked ${r.predicted_winner}`}
            >
              {r.is_correct ? "✓" : "✗"}
            </button>
          );
        })}
      </div>
      {selected && (
        <p className="caption pick-detail">
          {selected.game_date} — {selected.away_team} @ {selected.home_team}: picked{" "}
          <strong>{selected.predicted_winner}</strong>
          {finalScoreLabel(selected)
            ? ` · final ${finalScoreLabel(selected)}`
            : selected.actual_winner
              ? ` · ${selected.actual_winner} won`
              : ""}{" "}
          — {selected.is_correct ? "hit" : "miss"}
        </p>
      )}
    </>
  );
}
