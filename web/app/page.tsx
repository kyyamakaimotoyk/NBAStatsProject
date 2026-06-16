"use client";

import { useEffect, useState } from "react";
import { getLatestPredictions, type PredictionsResponse } from "@/lib/api";
import PredictionsTable from "@/components/PredictionsTable";

export default function HomePage() {
  const [data, setData] = useState<PredictionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Runs in the browser after the static HTML loads — this is the client-side
  // fetch that makes a static export behave like a live app.
  useEffect(() => {
    getLatestPredictions()
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error)
    return <p className="status error">Couldn&apos;t load predictions: {error}</p>;
  if (!data) return <p className="status">Loading predictions…</p>;
  if (data.count === 0)
    return (
      <p className="status">No predictions yet — check back after the next slate.</p>
    );

  return (
    <section>
      <h1>Predictions for {data.game_date}</h1>
      <PredictionsTable predictions={data.predictions} />
    </section>
  );
}
