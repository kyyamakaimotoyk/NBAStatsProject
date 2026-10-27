"use client";

import { useEffect, useMemo, useState } from "react";
import { getPerformanceResults, type AccuracySummary, type Prediction } from "@/lib/api";
import {
  summaryByModel,
  trendSeries,
  marketCompare,
  spreadRecord,
  classificationRates,
  confusionCounts,
  skillCurve,
  missCdf,
} from "@/lib/perf";
import { useLang } from "@/lib/i18n";
import TrendChart, { type TrendSeries } from "@/components/TrendChart";
import MarginScatter from "@/components/MarginScatter";
import PicksStrip from "@/components/PicksStrip";
import AccuracyBars from "@/components/AccuracyBars";
import ResultsTable from "@/components/ResultsTable";
import ConfusionMatrix from "@/components/ConfusionMatrix";
import PageGuide from "@/components/PageGuide";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };
const MARKET_COLOR = "#cbd5e1";

// Shown while the full results load: the 12-month per-model summary baked in
// at build time, so the prerendered page carries the headline numbers in
// prose rather than just a loading line.
function SummarySnapshot({ models }: { models: AccuracySummary[] }) {
  const { t } = useLang();
  const graded = models.filter((m) => m.accuracy !== null && m.total_predictions > 0);
  if (graded.length === 0) return null;
  return (
    <div className="snapshot">
      <h2>{t.accuracy.snapshotTitle}</h2>
      <ul>
        {graded.map((m) => (
          <li key={m.model_type}>
            {t.accuracy.snapshotLine(
              t.models[m.model_type] ?? m.model_type,
              m.correct_predictions,
              m.total_predictions,
              ((m.accuracy as number) * 100).toFixed(1),
              m.mae === null ? null : m.mae.toFixed(1),
            )}
          </li>
        ))}
      </ul>
      <p className="caption">{t.accuracy.snapshotCaption}</p>
    </div>
  );
}

export default function AccuracyContent({
  snapshot,
}: {
  // /api/accuracy/summary?days=365, baked at build time (null if unreachable).
  snapshot: AccuracySummary[] | null;
}) {
  const { t } = useLang();
  const [days, setDays] = useState(365);
  const [rows, setRows] = useState<Prediction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null); // null = auto (best)

  useEffect(() => {
    setRows(null);
    setError(null);
    getPerformanceResults(days)
      .then((r) => setRows(r.results))
      .catch((e) => setError(String(e)));
  }, [days]);

  const summaries = useMemo(() => (rows ? summaryByModel(rows) : []), [rows]);

  // Featured model: the user's pick, else the best performer with a real sample.
  const featured = useMemo(() => {
    if (model && summaries.some((s) => s.model === model)) return model;
    const scored = summaries.filter((s) => s.n >= 20);
    const pool = scored.length > 0 ? scored : summaries;
    if (pool.length === 0) return null;
    return pool.reduce((a, b) => (b.accuracyPct > a.accuracyPct ? b : a)).model;
  }, [model, summaries]);

  const featuredRows = useMemo(
    () => (rows && featured ? rows.filter((r) => r.model_type === featured) : []),
    [rows, featured],
  );
  const featuredSummary = summaries.find((s) => s.model === featured);
  const market = useMemo(() => marketCompare(featuredRows), [featuredRows]);
  const duel = useMemo(() => spreadRecord(featuredRows), [featuredRows]);
  const confusion = useMemo(() => confusionCounts(featuredRows), [featuredRows]);
  const trend = useMemo(() => (rows ? trendSeries(rows) : { data: [], models: [] }), [rows]);
  const skill = useMemo(() => (rows ? skillCurve(rows) : { data: [], models: [] }), [rows]);
  const cdf = useMemo(() => (rows ? missCdf(rows) : { data: [], models: [] }), [rows]);
  const cls = useMemo(() => (rows ? classificationRates(rows) : []), [rows]);
  const clsBars = cls.map((c) => ({
    name: c.key === "market" ? t.accuracy.marketFavorite : (t.models[c.key] ?? c.key),
    pct: c.pct,
    n: c.n,
    color: c.key === "market" ? MARKET_COLOR : (COLORS[c.key] ?? "#888"),
  }));

  const accSeries: TrendSeries[] = [
    ...trend.models.map((m) => ({
      key: `${m}_acc`,
      name: t.models[m] ?? m,
      color: COLORS[m] ?? "#888",
    })),
    // The benchmark rides along: the market favorite's hit rate on the same games.
    { key: "market_acc", name: t.accuracy.marketFavorite, color: MARKET_COLOR, dashed: true },
  ];
  const maeSeries: TrendSeries[] = [
    ...trend.models.map((m) => ({
      key: `${m}_mae`,
      name: t.models[m] ?? m,
      color: COLORS[m] ?? "#888",
    })),
    { key: "market_mae", name: t.accuracy.marketSeries, color: MARKET_COLOR, dashed: true },
  ];
  const skillSeries: TrendSeries[] = [
    ...skill.models.map((m) => ({
      key: m,
      name: t.models[m] ?? m,
      color: COLORS[m] ?? "#888",
    })),
    { key: "market", name: t.accuracy.marketFavorite, color: MARKET_COLOR, dashed: true },
  ];
  // Snap the skill-curve y-domain outward to 5s so the zero line sits on a tick.
  const skillVals = skill.data.flatMap((d) =>
    skillSeries.map((s) => Number(d[s.key])).filter(Number.isFinite),
  );
  const skillDomain: [number, number] = [
    Math.min(0, Math.floor(Math.min(...skillVals, 0) / 5) * 5),
    Math.max(5, Math.ceil(Math.max(...skillVals, 0) / 5) * 5),
  ];
  const cdfSeries: TrendSeries[] = [
    ...cdf.models.map((m) => ({
      key: m,
      name: t.models[m] ?? m,
      color: COLORS[m] ?? "#888",
    })),
    { key: "market", name: t.accuracy.marketSeries, color: MARKET_COLOR, dashed: true },
  ];
  const cdfData = cdf.data.map((d) => ({ ...d, x: t.accuracy.cdfTick(d.x as number) }));

  if (error || !rows) {
    return (
      <section>
        <h1>{t.accuracy.title}</h1>
        <p className="subtle">{t.accuracy.subtitle}</p>
        {snapshot && days === 365 && <SummarySnapshot models={snapshot} />}
        {error ? (
          <p className="status error">{t.accuracy.errLoad(error)}</p>
        ) : (
          <p className="status">{t.accuracy.loading}</p>
        )}
        <PageGuide page="accuracy" />
      </section>
    );
  }

  return (
    <section>
      <h1>{t.accuracy.title}</h1>
      <p className="subtle">{t.accuracy.subtitle}</p>

      <div className="controls explore-controls">
        <label>
          {t.accuracy.windowLabel}{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {t.accuracy.windows.map((w) => (
              <option key={w.days} value={w.days}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.accuracy.modelLabel}{" "}
          <select value={featured ?? ""} onChange={(e) => setModel(e.target.value)}>
            {summaries.map((s) => (
              <option key={s.model} value={s.model}>
                {t.models[s.model] ?? s.model}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!featuredSummary && <p className="status">{t.accuracy.noGraded}</p>}

      {featuredSummary && (
        <>
          <div className="cards">
            <div className="card">
              <div className="card-title">{t.accuracy.cardWinnerAcc}</div>
              <div className="card-metric">{featuredSummary.accuracyPct.toFixed(1)}%</div>
              <div className="card-sub">
                {t.accuracy.cardWinnerSub(t.models[featuredSummary.model] ?? featuredSummary.model)}
              </div>
            </div>
            <div className="card">
              <div className="card-title">{t.accuracy.cardMarginMiss}</div>
              <div className="card-metric">{t.common.plusMinusPts(featuredSummary.mae.toFixed(1))}</div>
              <div className="card-sub">{t.accuracy.cardMarginSub}</div>
            </div>
            {market && (
              <div className="card">
                <div className="card-title">{t.accuracy.cardMarket}</div>
                <div className="card-metric">{t.common.plusMinusPts(market.marketMae.toFixed(1))}</div>
                <div className="card-sub">
                  {t.accuracy.cardMarketSub(
                    market.modelMae.toFixed(1),
                    market.n.toLocaleString(),
                    featuredSummary.n.toLocaleString(),
                    market.closerPct,
                  )}
                </div>
              </div>
            )}
            {duel && (
              <div className="card">
                <div className="card-title">{t.accuracy.cardSpread}</div>
                <div className="card-metric">{duel.pct.toFixed(1)}%</div>
                <div className="card-sub">
                  {t.accuracy.cardSpreadSub(duel.w, duel.l, duel.ties)}
                </div>
              </div>
            )}
            <div className="card">
              <div className="card-title">{t.accuracy.cardGraded}</div>
              <div className="card-metric">{featuredSummary.n.toLocaleString()}</div>
              <div className="card-sub">{t.accuracy.cardGradedSub}</div>
            </div>
          </div>

          <h2>{t.accuracy.predVsActual}</h2>
          <MarginScatter rows={featuredRows} />
          <p className="caption">{t.accuracy.scatterCaption}</p>

          {confusion && (
            <>
              <div className="conf-row conf-row-single">
                <ConfusionMatrix
                  label={t.accuracy.pickGridTitle(t.models[featuredSummary.model] ?? featuredSummary.model)}
                  counts={confusion}
                  pickRows
                />
              </div>
              <p className="caption">{t.accuracy.pickGridCaption}</p>
            </>
          )}

          {clsBars.length > 1 && (
            <>
              <h2>{t.accuracy.clsTitle}</h2>
              <AccuracyBars data={clsBars} yLabel={t.charts.winnerAccuracyY} />
              <p className="caption">{t.accuracy.clsCaption}</p>
            </>
          )}

          <h2>{t.accuracy.recentPicks(t.models[featuredSummary.model] ?? featuredSummary.model)}</h2>
          <PicksStrip rows={featuredRows} />
          <p className="caption">
            {t.accuracy.picksCaption(Math.min(30, featuredRows.length))}
          </p>

          <h2>{t.accuracy.accOverTime}</h2>
          <TrendChart
            data={trend.data}
            series={accSeries}
            yUnit="%"
            yDomain={[0, 100]}
            refY={50}
            xLabel={t.charts.gameDate}
            yLabel={t.charts.winnerAccuracyY}
          />
          <p className="caption">{t.accuracy.accCaption}</p>

          {/* The cumulative counterpart to the noisy trailing rate above: gaps
              between models accumulate instead of washing out week to week.
              Shared with /performance — headings and caption live under t.perf. */}
          <h2>{t.perf.skillTitle}</h2>
          <TrendChart
            data={skill.data}
            series={skillSeries}
            yDomain={skillDomain}
            refY={0}
            xLabel={t.charts.gameDate}
            yLabel={t.perf.skillYLabel}
          />
          <p className="caption">{t.perf.skillCaption}</p>

          <h2>{t.accuracy.maeOverTime}</h2>
          <TrendChart
            data={trend.data}
            series={maeSeries}
            xLabel={t.charts.gameDate}
            yLabel={t.charts.marginMissY}
            yTickStep={5}
          />
          <p className="caption">{t.accuracy.maeCaption}</p>

          <h2>{t.accuracy.cdfTitle}</h2>
          <TrendChart
            data={cdfData}
            series={cdfSeries}
            xKey="x"
            yUnit="%"
            yDomain={[0, 100]}
            xLabel={t.accuracy.cdfXLabel}
            yLabel={t.accuracy.cdfYLabel}
          />
          <p className="caption">{t.accuracy.cdfCaption}</p>

          {/* The full receipts, all models side by side (heading lives under
              t.perf; the grade toggle and caption live inside the table). */}
          <h2>{t.perf.gameByGame}</h2>
          <ResultsTable rows={rows} />
        </>
      )}
      <PageGuide page="accuracy" />
    </section>
  );
}
