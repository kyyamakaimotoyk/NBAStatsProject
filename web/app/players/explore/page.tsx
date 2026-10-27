import type { Metadata } from "next";
import PlayerExploreContent from "./PlayerExploreContent";

export const metadata: Metadata = {
  title: "Player deep-dive",
  description:
    "One NBA player's game-by-game stats next to the model's projections: hit rates over any line, stat distributions, prediction error, and the next matchup.",
  alternates: { canonical: "/players/explore/" },
};

export default function Page() {
  return <PlayerExploreContent />;
}
