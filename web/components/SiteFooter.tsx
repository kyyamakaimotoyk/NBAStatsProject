"use client";

import { useLang } from "@/lib/i18n";

export default function SiteFooter() {
  const { t } = useLang();
  return <footer className="site-footer">{t.footer.disclaimer}</footer>;
}
