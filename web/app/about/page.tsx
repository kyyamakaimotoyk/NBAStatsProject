import type { Metadata } from "next";
import AboutContent from "./AboutContent";

export const metadata: Metadata = {
  title: "About",
  description:
    "How HoopModel works: the data, the models, the nightly cycle, and how every prediction gets graded in public.",
  alternates: { canonical: "/about/" },
};

// Metadata must stay in a server component; the prose itself is language-
// switched on the client, so it lives in AboutContent.
export default function AboutPage() {
  return <AboutContent />;
}
