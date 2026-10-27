import type { Metadata } from "next";
import ArticlesIndex from "./ArticlesIndex";

export const metadata: Metadata = {
  title: "Articles",
  description:
    "Findings from HoopModel's experiments: what makes NBA games predictable, what doesn't, and how we test whether a model change is real.",
  alternates: { canonical: "/articles/" },
};

export default function ArticlesPage() {
  return <ArticlesIndex />;
}
