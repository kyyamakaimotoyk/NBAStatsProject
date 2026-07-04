"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getLatestPredictions,
  getAccuracySummary,
  type PredictionsResponse,
  type AccuracySummary,
} from "@/lib/api";
import { MODEL_LABELS } from "@/lib/perf";
import PredictionsTable from "@/components/PredictionsTable";
import InjuryReport from "@/components/InjuryReport";

// Best-performing model with a meaningful sample — the headline the proof bar quotes.
function headlineModel(models: AccuracySummary[]): AccuracySummary | null {
  const scored = models.filter((m) => m.accuracy !== null && m.total_predictions >= 20);
  if (scored.length === 0) return null;
  return scored.reduce((a, b) => ((b.accuracy as number) > (a.accuracy as number) ? b : a));
}

function ProofBar({
  recent,
  season,
}: {
  recent: AccuracySummary[] | null;
  season: AccuracySummary[] | null;
}) {
  // Prefer the last-30-days window; in the offseason it's empty, so fall back
  // to the trailing year and label it honestly.
  const recentBest = recent ? headlineModel(recent) : null;
  const best = recentBest ?? (season ? headlineModel(season) : null);
  if (!best) return null;
  const windowLabel = recentBest ? "last 30 days" : "last season";
  const totalLogged = (season ?? []).reduce((s, m) => s + m.total_predictions, 0);

  return (
    <div className="proof-bar">
      <div className="proof-chip">
        <div className="proof-value">{Math.round((best.accuracy as number) * 100)}%</div>
        <div className="proof-label">
          winners called, {windowLabel}
          <br />({MODEL_LABELS[best.model_type] ?? best.model_type})
        </div>
      </div>
      {best.mae !== null && (
        <div className="proof-chip">
          <div className="proof-value">±{best.mae.toFixed(1)} pts</div>
          <div className="proof-label">
            average margin miss,
            <br />
            {windowLabel}
          </div>
        </div>
      )}
      {totalLogged > 0 && (
        <div className="proof-chip">
          <div className="proof-value">{totalLogged.toLocaleString()}</div>
          <div className="proof-label">
            predictions logged
            <br />
            and publicly scored
          </div>
        </div>
      )}
    </div>
  );
}

function GamesSection({ data, error }: { data: PredictionsResponse | null; error: string | null }) {
  if (error) return <p className="status error">Couldn&apos;t load predictions: {error}</p>;
  if (!data) return <p className="status">Loading predictions…</p>;

  const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local
  const stale = data.game_date !== null && data.game_date < today;

  if (data.count === 0 || (stale && data.predictions.length === 0)) {
    return (
      <div className="offseason">
        <h2>It&apos;s the offseason</h2>
        <p>
          Nightly picks return when the season tips off in October. Until then, the whole
          track record stays up — every prediction we&apos;ve made, scored against what
          actually happened.
        </p>
        <div className="links">
          <Link href="/accuracy">Last season&apos;s report card →</Link>
          <Link href="/explore">Explore the data →</Link>
        </div>
      </div>
    );
  }

  return (
    <>
      <h2 id="tonight">
        {stale ? `Latest slate — ${data.game_date}` : `Predictions for ${data.game_date}`}
      </h2>
      {stale && (
        <p className="subtle">
          No games tonight — this is the most recent slate the models predicted.
        </p>
      )}
      <PredictionsTable predictions={data.predictions} />
      {data.game_date && <InjuryReport date={data.game_date} />}
    </>
  );
}

export default function HomePage() {
  const [data, setData] = useState<PredictionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<AccuracySummary[] | null>(null);
  const [season, setSeason] = useState<AccuracySummary[] | null>(null);

  // Runs in the browser after the static HTML loads — this is the client-side
  // fetch that makes a static export behave like a live app. The proof bar is
  // best-effort: if its fetches fail we just don't render it.
  useEffect(() => {
    getLatestPredictions()
      .then(setData)
      .catch((e) => setError(String(e)));
    getAccuracySummary(30)
      .then((r) => setRecent(r.models))
      .catch(() => setRecent([]));
    getAccuracySummary(365)
      .then((r) => setSeason(r.models))
      .catch(() => setSeason([]));
  }, []);

  return (
    <section>
      <div className="hero">
        <h1>Nightly NBA predictions — with receipts.</h1>
        <p className="hero-sub">
          Three machine-learning models pick every NBA game. Every prediction is logged,
          scored against the real result, and published — hits and misses alike.
        </p>
        <div className="hero-ctas">
          <a className="btn primary" href="#tonight">
            Tonight&apos;s picks
          </a>
          <Link className="btn ghost" href="/accuracy">
            See the track record
          </Link>
        </div>
        <ProofBar recent={recent} season={season} />
      </div>

      <GamesSection data={data} error={error} />

      <h2>How it works</h2>
      <div className="how-strip">
        <div className="how-step">
          <div className="step-num">1</div>
          <h3>Box scores in</h3>
          <p>Every game&apos;s team stats — shooting, rebounding, hustle, tracking.</p>
        </div>
        <div className="how-step">
          <div className="step-num">2</div>
          <h3>Rolling form</h3>
          <p>Each team&apos;s recent play, distilled into rolling features.</p>
        </div>
        <div className="how-step">
          <div className="step-num">3</div>
          <h3>Three models</h3>
          <p>A random forest, gradient boosting and a neural net each pick a winner and a margin.</p>
        </div>
        <div className="how-step">
          <div className="step-num">4</div>
          <h3>Scored in public</h3>
          <p>
            Picks post nightly, then get graded against the final score.{" "}
            <Link href="/accuracy">The full record →</Link>
          </p>
        </div>
      </div>
      <p className="caption">
        Want the longer version — data, models, the nightly cycle?{" "}
        <Link href="/about">How HoopModel works →</Link>
      </p>
    </section>
  );
}
