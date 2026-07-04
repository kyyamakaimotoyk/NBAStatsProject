"use client";

import { useEffect, useMemo, useState } from "react";
import { getPerformanceResults, type Prediction } from "@/lib/api";
import {
  MODEL_LABELS,
  summaryByModel,
  trendSeries,
  homeAwaySplit,
  marketCompare,
} from "@/lib/perf";
import TrendChart, { type TrendSeries } from "@/components/TrendChart";
import MarginScatter from "@/components/MarginScatter";
import PicksStrip from "@/components/PicksStrip";

const COLORS: Record<string, string> = { rf: "#3b82f6", nn: "#22c55e", xgb: "#f59e0b" };
const MARKET_COLOR = "#cbd5e1";

const WINDOWS = [
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
  { days: 365, label: "Last 12 months" },
  { days: 1100, label: "Three seasons" },
];

export default function AccuracyPage() {
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
    name: MODEL_LABELS[m] ?? m,
    color: COLORS[m] ?? "#888",
  }));
  const maeSeries: TrendSeries[] = [
    ...trend.models.map((m) => ({
      key: `${m}_mae`,
      name: MODEL_LABELS[m] ?? m,
      color: COLORS[m] ?? "#888",
    })),
    { key: "market_mae", name: "Market closing line", color: MARKET_COLOR, dashed: true },
  ];

  if (error) return <p className="status error">Couldn&apos;t load the track record: {error}</p>;
  if (!rows) return <p className="status">Loading the track record…</p>;

  return (
    <section>
      <h1>Track record</h1>
      <p className="subtle">
        Every prediction is logged before tip-off and graded after the final buzzer.
        This page is the full scoreboard — nothing is edited after the fact.
      </p>

      <div className="controls explore-controls">
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
        <label>
          Model:{" "}
          <select value={featured ?? ""} onChange={(e) => setModel(e.target.value)}>
            {summaries.map((s) => (
              <option key={s.model} value={s.model}>
                {MODEL_LABELS[s.model] ?? s.model}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!featuredSummary && <p className="status">No graded games in this window yet.</p>}

      {featuredSummary && (
        <>
          <div className="cards">
            <div className="card">
              <div className="card-title">Winner accuracy</div>
              <div className="card-metric">{featuredSummary.accuracyPct.toFixed(1)}%</div>
              <div className="card-sub">
                {MODEL_LABELS[featuredSummary.model] ?? featuredSummary.model} · a coin flip is
                50%
              </div>
            </div>
            <div className="card">
              <div className="card-title">Average margin miss</div>
              <div className="card-metric">±{featuredSummary.mae.toFixed(1)} pts</div>
              <div className="card-sub">how far the predicted margin lands from the real one</div>
            </div>
            {market && (
              <div className="card">
                <div className="card-title">Market closing line</div>
                <div className="card-metric">±{market.marketMae.toFixed(1)} pts</div>
                <div className="card-sub">
                  vs our ±{market.modelMae.toFixed(1)} — paired on the{" "}
                  {market.n.toLocaleString()} of {featuredSummary.n.toLocaleString()} graded
                  games with a line · we were closer on {market.closerPct}%
                </div>
              </div>
            )}
            <div className="card">
              <div className="card-title">Games graded</div>
              <div className="card-metric">{featuredSummary.n.toLocaleString()}</div>
              <div className="card-sub">in this window</div>
            </div>
          </div>

          <h2>Recent picks — {MODEL_LABELS[featuredSummary.model] ?? featuredSummary.model}</h2>
          <PicksStrip rows={featuredRows} />
          <p className="caption">
            The last {Math.min(30, featuredRows.length)} graded picks, oldest to newest. Hover a
            square for the game.
          </p>

          <h2>Winner accuracy over time</h2>
          <TrendChart
            data={trend.data}
            series={accSeries}
            yUnit="%"
            yDomain={[0, 100]}
            refY={50}
            xLabel="Game date"
            yLabel="Winner accuracy"
          />
          <p className="caption">
            Each point is the trailing 7 days of games. The dashed line is 50% — coin-flip
            territory.
          </p>

          <h2>Margin error over time</h2>
          <TrendChart
            data={trend.data}
            series={maeSeries}
            xLabel="Game date"
            yLabel="Average margin miss (pts)"
            yTickStep={5}
          />
          <p className="caption">
            Average points missed by, trailing 7 days — lower is better. The dashed line is the
            betting market&apos;s closing spread on the same games: the strongest public
            benchmark for a game&apos;s margin. We show it to keep ourselves honest, not to sell
            picks.
          </p>

          <h2>Predicted vs actual margin</h2>
          <MarginScatter rows={featuredRows} />
          <p className="caption">
            One point per game (home-team perspective). On the dashed diagonal, the prediction
            was exact; green points are games where the winner was still called correctly.
          </p>

          {split && (
            <>
              <h2>Home picks vs away picks</h2>
              <div className="cards">
                <div className="card">
                  <div className="card-title">When we pick the home team</div>
                  <div className="card-metric">{split.home.pct}%</div>
                  <div className="card-sub">correct, across {split.home.n} picks</div>
                </div>
                <div className="card">
                  <div className="card-title">When we pick the away team</div>
                  <div className="card-metric">{split.away.pct}%</div>
                  <div className="card-sub">correct, across {split.away.n} picks</div>
                </div>
              </div>
              <p className="caption">
                A sanity check on home-court bias: if the model only ever trusted home teams,
                the away column would collapse.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
