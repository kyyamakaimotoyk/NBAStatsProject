"use client";

import { useEffect, useState } from "react";
import { getPerformanceResults, type Prediction } from "@/lib/api";
import {
  summaryByModel,
  confidenceBuckets,
  agreementSplit,
  skillCurve,
  marginErrorHist,
  calibrationBins,
  rocCurve,
  confusionCounts,
  marketConfusionCounts,
} from "@/lib/perf";
import { useLang } from "@/lib/i18n";
import PerfLineChart from "@/components/PerfLineChart";
import RocChart, { type RocCurveData } from "@/components/RocChart";
import ConfusionMatrix from "@/components/ConfusionMatrix";
import ResultsTable from "@/components/ResultsTable";
import BucketBars from "@/components/BucketBars";
import AccuracyBars from "@/components/AccuracyBars";
import ErrorHistogram from "@/components/ErrorHistogram";
import TrendChart, { type TrendSeries } from "@/components/TrendChart";
import PageGuide from "@/components/PageGuide";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };
const MARKET_COLOR = "#cbd5e1";
// Agreement classes are one measure, not competing entities — a single
// neutral hue keeps them from reading as a fourth, fifth and sixth model.
const AGREE_COLOR = "#94a3b8";

export default function PerformanceContent() {
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

          <h2>{t.perf.confTitle}</h2>
          {(() => {
            const cb = confidenceBuckets(rows);
            return (
              <BucketBars
                data={cb.data}
                series={cb.models.map((m) => ({
                  key: m,
                  name: t.models[m] ?? m,
                  color: COLORS[m] ?? "#888",
                }))}
                xKey="bucket"
                xLabel={t.perf.confXLabel}
                yLabel={t.charts.winnerAccuracyY}
                gamesLabel={t.perf.nGames}
              />
            );
          })()}
          <p className="caption">{t.perf.confCaption}</p>

          {(() => {
            const agree = agreementSplit(rows);
            if (agree.length === 0) return null;
            return (
              <>
                <h2>{t.perf.agreeTitle}</h2>
                <AccuracyBars
                  data={agree.map((a) => ({
                    name: t.perf.agree[a.key],
                    pct: a.pct,
                    n: a.n,
                    color: AGREE_COLOR,
                  }))}
                  yLabel={t.charts.winnerAccuracyY}
                />
                <p className="caption">{t.perf.agreeCaption}</p>
              </>
            );
          })()}

          <h2>{t.perf.skillTitle}</h2>
          {(() => {
            const sc = skillCurve(rows);
            const series: TrendSeries[] = [
              ...sc.models.map((m) => ({
                key: m,
                name: t.models[m] ?? m,
                color: COLORS[m] ?? "#888",
              })),
              { key: "market", name: t.accuracy.marketFavorite, color: MARKET_COLOR, dashed: true },
            ];
            const vals = sc.data.flatMap((d) =>
              series.map((s) => Number(d[s.key])).filter(Number.isFinite),
            );
            const lo = Math.min(0, Math.floor(Math.min(...vals, 0) / 5) * 5);
            const hi = Math.max(5, Math.ceil(Math.max(...vals, 0) / 5) * 5);
            return (
              <TrendChart
                data={sc.data}
                series={series}
                yDomain={[lo, hi]}
                refY={0}
                xLabel={t.charts.gameDate}
                yLabel={t.perf.skillYLabel}
              />
            );
          })()}
          <p className="caption">{t.perf.skillCaption}</p>

          <h2>{t.perf.histTitle}</h2>
          <ErrorHistogram
            panels={marginErrorHist(rows).map((h) => ({
              label: t.models[h.model] ?? h.model,
              color: COLORS[h.model] ?? "#888",
              n: h.n,
              bins: h.bins,
            }))}
            xLabel={t.perf.histXLabel}
            gamesLabel={t.perf.nGames}
          />
          <p className="caption">{t.perf.histCaption}</p>

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
            {(() => {
              const mkt = marketConfusionCounts(rows);
              return mkt ? (
                <ConfusionMatrix label={t.accuracy.marketFavorite} counts={mkt} />
              ) : null;
            })()}
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
        </>
      )}
      <PageGuide page="performance" />
    </section>
  );
}
