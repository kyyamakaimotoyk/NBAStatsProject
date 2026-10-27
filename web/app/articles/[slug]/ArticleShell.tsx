"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";
import type { Article } from "@/lib/articles";

// Language-aware chrome around server-rendered article bodies: title, byline,
// the body in the reader's language, and — when an article has no Japanese
// body yet — the English one with a notice for Japanese readers.
export default function ArticleShell({
  article,
  en,
  ja,
}: {
  article: Article;
  en: React.ReactNode;
  ja: React.ReactNode | null;
}) {
  const { lang, t } = useLang();
  const showJa = lang === "ja" && ja !== null;
  return (
    <article className="article">
      <p className="article-back">
        <Link href="/articles/">{t.articles.back}</Link>
      </p>
      <h1>{article.title[lang]}</h1>
      <p className="article-meta">
        {t.articles.byline} · {article.date} · {t.articles.readTime(article.readMinutes)}
      </p>
      {lang === "ja" && !showJa && (
        <p className="article-notice">{t.articles.englishOnlyNotice}</p>
      )}
      <div className="article-body">{showJa ? ja : en}</div>
    </article>
  );
}
