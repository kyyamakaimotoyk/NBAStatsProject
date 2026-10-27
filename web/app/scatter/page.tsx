import type { Metadata } from "next";
import ScatterContent from "./ScatterContent";

export const metadata: Metadata = {
  title: "Stat scatter",
  description:
    "Plot any two NBA team stats against each other, one point per team-game, colored by win or loss, with a regression line and per-team distributions.",
  alternates: { canonical: "/scatter/" },
};

export default function Page() {
  return <ScatterContent />;
}
