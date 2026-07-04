"use client";

import { useEffect, useMemo, useState } from "react";
import { getPerformanceResults, type Prediction } from "@/lib/api";
import {
  summaryByModel,
  trendSeries,
  homeAwaySplit,
  marketCompare,
} from "@/lib/perf";
import { useLang } from "@/lib/i18n";
import TrendChart, { type TrendSeries } from "@/components/TrendChart";
import MarginScatter from "@/components/MarginScatter";
import PicksStrip from "@/components/PicksStrip";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };
const MARKET_COLOR = "#cbd5e1";

export default function AccuracyPage() {
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
  const split = useMemo(() => homeAwaySplit(featuredRows), [featuredRows]);
  const trend = useMemo(() => (rows ? trendSeries(rows) : { data: [], models: [] }), [rows]);

  const accSeries: TrendSeries[] = trend.models.map((m) => ({
    key: `${m}_acc`,
    name: t.models[m] ?? m,
    color: COLORS[m] ?? "#888",
  }));
  const maeSeries: TrendSeries[] = [
    ...trend.models.map((m) => ({
      key: `${m}_mae`,
      name: t.models[m] ?? m,
      color: COLORS[m] ?? "#888",
    })),
    { key: "market_mae", name: t.accuracy.marketSeries, color: MARKET_COLOR, dashed: true },
  ];

  if (error) return <p className="status error">{t.accuracy.errLoad(error)}</p>;
  if (!rows) return <p className="status">{t.accuracy.loading}</p>;

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
            <div className="card">
              <div className="card-title">{t.accuracy.cardGraded}</div>
              <div className="card-metric">{featuredSummary.n.toLocaleString()}</div>
              <div className="card-sub">{t.accuracy.cardGradedSub}</div>
            </div>
          </div>

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

          <h2>{t.accuracy.maeOverTime}</h2>
          <TrendChart
            data={trend.data}
            series={maeSeries}
            xLabel={t.charts.gameDate}
            yLabel={t.charts.marginMissY}
            yTickStep={5}
          />
          <p className="caption">{t.accuracy.maeCaption}</p>

          <h2>{t.accuracy.predVsActual}</h2>
          <MarginScatter rows={featuredRows} />
          <p className="caption">{t.accuracy.scatterCaption}</p>

          {split && (
            <>
              <h2>{t.accuracy.homeAway}</h2>
              <div className="cards">
                <div className="card">
                  <div className="card-title">{t.accuracy.pickHome}</div>
                  <div className="card-metric">{split.home.pct}%</div>
                  <div className="card-sub">{t.accuracy.correctAcross(split.home.n)}</div>
                </div>
                <div className="card">
                  <div className="card-title">{t.accuracy.pickAway}</div>
                  <div className="card-metric">{split.away.pct}%</div>
                  <div className="card-sub">{t.accuracy.correctAcross(split.away.n)}</div>
                </div>
              </div>
              <p className="caption">{t.accuracy.homeAwayCaption}</p>
            </>
          )}
        </>
      )}
    </section>
  );
}
