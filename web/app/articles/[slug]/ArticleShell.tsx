"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";
import type { Article } from "@/lib/articles";

// Language-aware chrome around a server-rendered article body: title, byline,
// and — while a body is English-only — a notice for Japanese readers.
export default function ArticleShell({
  article,
  children,
}: {
  article: Article;
  children: React.ReactNode;
}) {
  const { lang, t } = useLang();
  return (
    <article className="article">
      <p className="article-back">
        <Link href="/articles/">{t.articles.back}</Link>
      </p>
      <h1>{article.title[lang]}</h1>
      <p className="article-meta">
        {t.articles.byline} · {article.date} · {t.articles.readTime(article.readMinutes)}
      </p>
      {lang === "ja" && !article.hasJapanese && (
        <p className="article-notice">{t.articles.englishOnlyNotice}</p>
      )}
      <div className="article-body">{children}</div>
    </article>
  );
}
