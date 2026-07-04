"use client";

import { useEffect, useState } from "react";
import { getPerformanceResults, type Prediction } from "@/lib/api";
import {
  summaryByModel,
  dailyAccuracy,
  calibrationBins,
  rocCurve,
  confusionCounts,
} from "@/lib/perf";
import { useLang } from "@/lib/i18n";
import PerfLineChart from "@/components/PerfLineChart";
import ResultsTable from "@/components/ResultsTable";
import RocChart, { type RocCurveData } from "@/components/RocChart";
import ConfusionMatrix from "@/components/ConfusionMatrix";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };

export default function PerformancePage() {
  const { t } = useLang();
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
      <h1>{t.perf.title}</h1>
      <p className="subtle">{t.perf.subtitle}</p>

      <div className="controls">
        <label>
          {t.perf.windowLabel}{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {t.perf.windows.map((w) => (
              <option key={w.days} value={w.days}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="status error">{t.perf.errLoad(error)}</p>}
      {!error && !rows && <p className="status">{t.perf.loading}</p>}
      {!error && rows && rows.length === 0 && (
        <p className="status">{t.perf.noCompleted}</p>
      )}

      {!error && rows && rows.length > 0 && (
        <>
          <div className="cards">
            {summaryByModel(rows).map((s) => (
              <div className="card" key={s.model}>
                <div className="card-title">{t.models[s.model] ?? s.model}</div>
                <div className="card-metric">{s.accuracyPct.toFixed(1)}%</div>
                <div className="card-sub">{t.perf.accuracyGames(s.n)}</div>
                <div className="card-row">
                  {t.perf.maeCalib(s.mae.toFixed(1), s.calibrationErr.toFixed(3))}
                </div>
              </div>
            ))}
          </div>

          <h2>{t.perf.dailyAcc}</h2>
          {(() => {
            const d = dailyAccuracy(rows);
            return (
              <PerfLineChart
                data={d.data}
                models={d.models}
                xKey="date"
                xLabel={t.charts.gameDate}
                yLabel={t.charts.dailyWinnerAccuracyY}
              />
            );
          })()}

          <h2>{t.perf.calibration}</h2>
          {(() => {
            const c = calibrationBins(rows);
            return (
              <PerfLineChart
                data={c.data}
                models={c.models}
                xKey="x"
                numericX
                diagonal
                xLabel={t.perf.calibXLabel}
                yLabel={t.charts.actualHomeWinRateY}
              />
            );
          })()}

          <h2>{t.perf.roc}</h2>
          {(() => {
            const models = [...new Set(rows.map((r) => r.model_type))].sort();
            const curves: RocCurveData[] = [];
            for (const m of models) {
              const roc = rocCurve(rows.filter((r) => r.model_type === m));
              if (roc)
                curves.push({
                  model: m,
                  label: t.models[m] ?? m,
                  color: COLORS[m] ?? "#888",
                  auc: roc.auc,
                  points: roc.points,
                });
            }
            return <RocChart curves={curves} />;
          })()}
          <p className="caption">{t.perf.rocCaption}</p>

          <h2>{t.perf.confusion}</h2>
          <div className="conf-row">
            {[...new Set(rows.map((r) => r.model_type))].sort().map((m) => {
              const counts = confusionCounts(rows.filter((r) => r.model_type === m));
              return counts ? (
                <ConfusionMatrix key={m} label={t.models[m] ?? m} counts={counts} />
              ) : null;
            })}
          </div>
          <p className="caption">{t.perf.confusionCaption}</p>

          <h2>{t.perf.gameByGame}</h2>
          <ResultsTable rows={rows} />
          <p className="caption">{t.perf.resultsCaption}</p>
        </>
      )}
    </section>
  );
}
