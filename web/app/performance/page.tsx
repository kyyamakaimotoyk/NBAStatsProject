import type { Metadata } from "next";
import PerformanceContent from "./PerformanceContent";

export const metadata: Metadata = {
  title: "Compare models",
  description:
    "Random forest vs XGBoost vs neural net on completed NBA games: calibration, ROC curves, confidence bands, agreement splits, and the game-by-game record.",
  alternates: { canonical: "/performance/" },
};

export default function Page() {
  return <PerformanceContent />;
}
