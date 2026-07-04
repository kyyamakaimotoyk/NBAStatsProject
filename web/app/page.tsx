"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getLatestPredictions,
  getAccuracySummary,
  type PredictionsResponse,
  type AccuracySummary,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";
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
  const { t } = useLang();
  // Prefer the last-30-days window; in the offseason it's empty, so fall back
  // to the trailing year and label it honestly.
  const recentBest = recent ? headlineModel(recent) : null;
  const best = recentBest ?? (season ? headlineModel(season) : null);
  if (!best) return null;
  const windowLabel = recentBest ? t.home.windowLast30 : t.home.windowLastSeason;
  const totalLogged = (season ?? []).reduce((s, m) => s + m.total_predictions, 0);

  return (
    <div className="proof-bar">
      <div className="proof-chip">
        <div className="proof-value">{Math.round((best.accuracy as number) * 100)}%</div>
        <div className="proof-label">
          {t.home.proofWinners(windowLabel)}
          <br />({t.models[best.model_type] ?? best.model_type})
        </div>
      </div>
      {best.mae !== null && (
        <div className="proof-chip">
          <div className="proof-value">{t.common.plusMinusPts(best.mae.toFixed(1))}</div>
          <div className="proof-label">
            {t.home.proofMarginLine1}
            <br />
            {windowLabel}
          </div>
        </div>
      )}
      {totalLogged > 0 && (
        <div className="proof-chip">
          <div className="proof-value">{totalLogged.toLocaleString()}</div>
          <div className="proof-label">
            {t.home.proofLoggedLine1}
            <br />
            {t.home.proofLoggedLine2}
          </div>
        </div>
      )}
    </div>
  );
}

function GamesSection({ data, error }: { data: PredictionsResponse | null; error: string | null }) {
  const { t } = useLang();
  if (error) return <p className="status error">{t.home.errLoad(error)}</p>;
  if (!data) return <p className="status">{t.home.loading}</p>;

  const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local
  const stale = data.game_date !== null && data.game_date < today;

  if (data.count === 0 || (stale && data.predictions.length === 0)) {
    return (
      <div className="offseason">
        <h2>{t.home.offseasonTitle}</h2>
        <p>{t.home.offseasonBody}</p>
        <div className="links">
          <Link href="/accuracy">{t.home.offseasonLinkRecord}</Link>
          <Link href="/explore">{t.home.offseasonLinkExplore}</Link>
        </div>
      </div>
    );
  }

  return (
    <>
      <h2 id="tonight">
        {stale
          ? t.home.latestSlate(data.game_date ?? "")
          : t.home.predictionsFor(data.game_date ?? "")}
      </h2>
      {stale && <p className="subtle">{t.home.staleNote}</p>}
      <PredictionsTable predictions={data.predictions} />
      {data.game_date && <InjuryReport date={data.game_date} />}
    </>
  );
}

export default function HomePage() {
  const { t } = useLang();
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
        <h1>{t.home.heroTitle}</h1>
        <p className="hero-sub">{t.home.heroSub}</p>
        <div className="hero-ctas">
          <a className="btn primary" href="#tonight">
            {t.home.ctaTonight}
          </a>
          <Link className="btn ghost" href="/accuracy">
            {t.home.ctaRecord}
          </Link>
        </div>
        <ProofBar recent={recent} season={season} />
      </div>

      <GamesSection data={data} error={error} />

      <h2>{t.home.howTitle}</h2>
      <div className="how-strip">
        <div className="how-step">
          <div className="step-num">1</div>
          <h3>{t.home.step1Title}</h3>
          <p>{t.home.step1Body}</p>
        </div>
        <div className="how-step">
          <div className="step-num">2</div>
          <h3>{t.home.step2Title}</h3>
          <p>{t.home.step2Body}</p>
        </div>
        <div className="how-step">
          <div className="step-num">3</div>
          <h3>{t.home.step3Title}</h3>
          <p>{t.home.step3Body}</p>
        </div>
        <div className="how-step">
          <div className="step-num">4</div>
          <h3>{t.home.step4Title}</h3>
          <p>
            {t.home.step4Body} <Link href="/accuracy">{t.home.step4Link}</Link>
          </p>
        </div>
      </div>
      <p className="caption">
        {t.home.longerVersion} <Link href="/about">{t.home.howLink}</Link>
      </p>
    </section>
  );
}
