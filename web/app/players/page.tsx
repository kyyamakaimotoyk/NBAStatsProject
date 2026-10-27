import type { Metadata } from "next";
import PlayersContent from "./PlayersContent";
import { bakePlayerDailyLatest } from "@/lib/serverData";

export const metadata: Metadata = {
  title: "Player projections",
  description:
    "Projected points, rebounds, assists and more for every NBA rotation player on tonight's slate, with the pace and defensive context behind each number.",
  alternates: { canonical: "/players/" },
};

// Build time: bake the latest slate into the HTML; the client refreshes it.
export default async function Page() {
  return <PlayersContent initialData={await bakePlayerDailyLatest()} />;
}
