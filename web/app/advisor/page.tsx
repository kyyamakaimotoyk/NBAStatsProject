import type { Metadata } from "next";
import AdvisorContent from "./AdvisorContent";

export const metadata: Metadata = {
  title: "Fantasy advisor",
  description:
    "Ask fantasy basketball start/sit, waiver, trade and keeper questions; answers are grounded in HoopModel's nightly player projections and season stats.",
  alternates: { canonical: "/advisor/" },
};

export default function Page() {
  return <AdvisorContent />;
}
