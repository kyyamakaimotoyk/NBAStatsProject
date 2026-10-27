import type { Metadata } from "next";
import HomeContent from "./HomeContent";
import { bakeAccuracySummary, bakeLatestPredictions } from "@/lib/serverData";

export const metadata: Metadata = {
  description:
    "Nightly machine-learning predictions for every NBA game from three models, each one logged before tip-off and graded in public against the final score.",
  alternates: { canonical: "/" },
};

// Runs at build time: the latest slate and the proof-bar numbers are baked
// into the static HTML, then HomeContent refreshes them in the browser.
export default async function Page() {
  const [latest, recent, season] = await Promise.all([
    bakeLatestPredictions(),
    bakeAccuracySummary(30),
    bakeAccuracySummary(365),
  ]);
  return (
    <HomeContent
      initialData={latest}
      initialRecent={recent?.models ?? null}
      initialSeason={season?.models ?? null}
    />
  );
}
