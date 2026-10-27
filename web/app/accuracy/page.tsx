import type { Metadata } from "next";
import AccuracyContent from "./AccuracyContent";
import { bakeAccuracySummary } from "@/lib/serverData";

export const metadata: Metadata = {
  title: "Track record",
  description:
    "Every HoopModel NBA prediction graded against the final score: winner accuracy, margin error, and a side-by-side comparison with the betting market's closing line.",
  alternates: { canonical: "/accuracy/" },
};

// Build time: bake the 12-month summary so the page has numbers before the
// (much larger) full results load in the browser.
export default async function Page() {
  const summary = await bakeAccuracySummary(365);
  return <AccuracyContent snapshot={summary?.models ?? null} />;
}
