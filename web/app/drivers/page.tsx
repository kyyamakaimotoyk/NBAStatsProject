import type { Metadata } from "next";
import DriversContent from "./DriversContent";

export const metadata: Metadata = {
  title: "What wins games",
  description:
    "Which rolling NBA team stats actually track a game's final margin? Correlations for every model feature, by home, away and differential.",
  alternates: { canonical: "/drivers/" },
};

export default function Page() {
  return <DriversContent />;
}
