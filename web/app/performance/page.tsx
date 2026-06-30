"use client";

import { useEffect, useState } from "react";
import { getPerformanceResults, type Prediction } from "@/lib/api";
import { summaryByModel, dailyAccuracy, calibrationBins, MODEL_LABELS } from "@/lib/perf";
import PerfLineChart from "@/components/PerfLineChart";
import ResultsTable from "@/components/ResultsTable";

const WINDOWS = [
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "180 days", days: 180 },
  { label: "Full season", days: 365 },
];

export default function PerformancePage() {
  const [rows, setRows] = useState<Prediction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(90);

  useEffect(() => {
    setRows(null);
    setError(null);
    getPerformanceResults(days)
      .then((r) => setRows(r.results))
      .catch((e) => setError(String(e)));
  }, [days]);

  return (
    <section>
      <h1>Model performance</h1>
      <p className="subtle">
        How each model has actually done on completed games — accuracy, calibration, and
        the game-by-game record.
      </p>

      <div className="controls">
        <label>
          Window:{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {WINDOWS.map((w) => (
              <option key={w.days} value={w.days}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="status error">Couldn&apos;t load performance: {error}</p>}
      {!error && !rows && <p className="status">Loading performance…</p>}
      {!error && rows && rows.length === 0 && (
        <p className="status">No completed games in this window yet.</p>
      )}

      {!error && rows && rows.length > 0 && (
        <>
          <div className="cards">
            {summaryByModel(rows).map((s) => (
              <div className="card" key={s.model}>
                <div className="card-title">{MODEL_LABELS[s.model] ?? s.model}</div>
                <div className="card-metric">{s.accuracyPct.toFixed(1)}%</div>
                <div className="card-sub">accuracy · {s.n} games</div>
                <div className="card-row">
                  MAE {s.mae.toFixed(1)} · calib err {s.calibrationErr.toFixed(3)}
                </div>
              </div>
            ))}
          </div>

          <h2>Daily win-prediction accuracy</h2>
          {(() => {
            const d = dailyAccuracy(rows);
            return <PerfLineChart data={d.data} models={d.models} xKey="date" />;
          })()}

          <h2>Calibration — predicted win prob vs. actual home-win rate</h2>
          {(() => {
            const c = calibrationBins(rows);
            return (
              <PerfLineChart
                data={c.data}
                models={c.models}
                xKey="x"
                numericX
                diagonal
                xLabel="Predicted home win %"
              />
            );
          })()}

          <h2>Recent results</h2>
          <ResultsTable rows={rows} />
        </>
      )}
    </section>
  );
}
