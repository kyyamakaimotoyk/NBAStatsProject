"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { ARTICLES } from "@/lib/articles";

export default function ArticlesIndex() {
  const { lang, t } = useLang();
  return (
    <section>
      <h1>{t.articles.title}</h1>
      <p className="subtle">{t.articles.subtitle}</p>
      <ul className="article-list">
        {ARTICLES.map((a) => (
          <li key={a.slug}>
            <Link href={`/articles/${a.slug}/`}>
              <h2>{a.title[lang]}</h2>
            </Link>
            <p className="article-meta">
              {a.date} · {t.articles.readTime(a.readMinutes)}
              {lang === "ja" && !a.hasJapanese && ` · ${t.articles.englishOnlyTag}`}
            </p>
            <p>{a.summary[lang]}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
