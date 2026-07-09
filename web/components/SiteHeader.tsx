"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";
import type { Lang } from "@/lib/translations";

export default function SiteHeader() {
  const { lang, setLang, t } = useLang();

  const langButton = (l: Lang, label: string) => (
    <button
      type="button"
      className={lang === l ? "active" : ""}
      aria-pressed={lang === l}
      onClick={() => setLang(l)}
    >
      {label}
    </button>
  );

  return (
    <header className="site-header">
      <div className="brand-row">
        <Link href="/" className="brand">
          HoopModel
        </Link>
        <div className="lang-toggle" aria-label="Language / 言語">
          {langButton("en", "EN")}
          {langButton("ja", "日本語")}
        </div>
      </div>
      <nav>
        <Link href="/">{t.nav.tonight}</Link>
        <Link href="/accuracy">{t.nav.trackRecord}</Link>
        <Link href="/performance">{t.nav.modelLab}</Link>
        <Link href="/explore">{t.nav.explore}</Link>
        <Link href="/scatter">{t.nav.scatter}</Link>
        <Link href="/players/explore">{t.nav.players}</Link>
        <Link href="/drivers">{t.nav.drivers}</Link>
        <Link href="/about">{t.nav.about}</Link>
      </nav>
    </header>
  );
}
