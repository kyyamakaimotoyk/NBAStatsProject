import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ARTICLES, getArticle } from "@/lib/articles";
import ArticleShell from "./ArticleShell";
import SignalOrNoise from "@/components/articles/SignalOrNoise";
import MarginFloor from "@/components/articles/MarginFloor";
import ImpactRatings from "@/components/articles/ImpactRatings";
import PlayoffPredictability from "@/components/articles/PlayoffPredictability";

// Article bodies by slug (metadata lives in lib/articles.ts).
const BODIES: Record<string, () => React.ReactNode> = {
  "signal-or-noise": SignalOrNoise,
  "margin-floor": MarginFloor,
  "impact-ratings": ImpactRatings,
  "playoff-predictability": PlayoffPredictability,
};

// Static export: every article is prerendered; unknown slugs 404.
export const dynamicParams = false;

export function generateStaticParams() {
  return ARTICLES.map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const article = getArticle((await params).slug);
  if (!article) return {};
  return {
    title: article.title.en,
    description: article.summary.en,
    alternates: { canonical: `/articles/${article.slug}/` },
    openGraph: { type: "article", publishedTime: article.date },
  };
}

export default async function ArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const article = getArticle(slug);
  const Body = BODIES[slug];
  if (!article || !Body) notFound();
  return (
    <ArticleShell article={article}>
      <Body />
    </ArticleShell>
  );
}
