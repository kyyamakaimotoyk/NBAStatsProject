"use client";

import { useEffect, useState } from "react";
import {
  getRollingAccuracy,
  getAccuracySummary,
  type RollingResponse,
  type AccuracySummaryResponse,
} from "@/lib/api";
import AccuracyChart from "@/components/AccuracyChart";

export default function AccuracyPage() {
  const [rolling, setRolling] = useState<RollingResponse | null>(null);
  const [summary, setSummary] = useState<AccuracySummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fire both requests at once; render when both resolve.
    Promise.all([getRollingAccuracy(90), getAccuracySummary(30)])
      .then(([r, s]) => {
        setRolling(r);
        setSummary(s);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error)
    return <p className="status error">Couldn&apos;t load accuracy: {error}</p>;
  if (!rolling || !summary)
    return <p className="status">Loading accuracy…</p>;

  return (
    <section>
      <h1>Historical accuracy</h1>

      <h2>Last 30 days</h2>
      <table className="pred-table">
        <thead>
          <tr>
            <th>Model</th>
            <th>Games</th>
            <th>Accuracy</th>
            <th>MAE</th>
          </tr>
        </thead>
        <tbody>
          {summary.models.map((m) => (
            <tr key={m.model_type}>
              <td>{m.model_type}</td>
              <td>{m.total_predictions}</td>
              <td>
                {m.accuracy === null
                  ? "—"
                  : `${Math.round(m.accuracy * 100)}%`}
              </td>
              <td>{m.mae === null ? "—" : m.mae.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Daily win-prediction accuracy (90 days)</h2>
      <AccuracyChart points={rolling.points} />
    </section>
  );
}
