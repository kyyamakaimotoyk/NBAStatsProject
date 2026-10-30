import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ARTICLES, getArticle } from "@/lib/articles";
import ArticleShell from "./ArticleShell";
import { EarlySeasonEn, EarlySeasonJa } from "@/components/articles/EarlySeason";
import { WinProbabilityEn, WinProbabilityJa } from "@/components/articles/WinProbability";
import { SignalOrNoiseEn, SignalOrNoiseJa } from "@/components/articles/SignalOrNoise";
import { MarginFloorEn, MarginFloorJa } from "@/components/articles/MarginFloor";
import { ImpactRatingsEn, ImpactRatingsJa } from "@/components/articles/ImpactRatings";
import {
  PlayoffPredictabilityEn,
  PlayoffPredictabilityJa,
} from "@/components/articles/PlayoffPredictability";

type Body = () => React.ReactNode;

// Article bodies by slug (metadata lives in lib/articles.ts). `ja` is optional:
// without it, Japanese readers get the English body plus a notice.
const BODIES: Record<string, { en: Body; ja?: Body }> = {
  "win-probability": { en: WinProbabilityEn, ja: WinProbabilityJa },
  "early-season": { en: EarlySeasonEn, ja: EarlySeasonJa },
  "signal-or-noise": { en: SignalOrNoiseEn, ja: SignalOrNoiseJa },
  "margin-floor": { en: MarginFloorEn, ja: MarginFloorJa },
  "impact-ratings": { en: ImpactRatingsEn, ja: ImpactRatingsJa },
  "playoff-predictability": { en: PlayoffPredictabilityEn, ja: PlayoffPredictabilityJa },
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
  const body = BODIES[slug];
  if (!article || !body) notFound();
  const { en: En, ja: Ja } = body;
  // Both versions are rendered here on the server; the shell picks one by the
  // reader's language. The prerendered HTML carries the English body.
  return <ArticleShell article={article} en={<En />} ja={Ja ? <Ja /> : null} />;
}
