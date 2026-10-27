import type { Metadata } from "next";
import ExploreContent from "./ExploreContent";

export const metadata: Metadata = {
  title: "Team stat trends",
  description:
    "Chart any NBA team's rolling 5- or 10-game form for box-score, four-factor, hustle and tracking stats, across up to three seasons.",
  alternates: { canonical: "/explore/" },
};

export default function Page() {
  return <ExploreContent />;
}
