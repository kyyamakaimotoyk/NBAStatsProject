"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";

export default function SiteFooter() {
  const { t } = useLang();
  return (
    <footer className="site-footer">
      {t.footer.disclaimer} <Link href="/privacy">{t.footer.privacy}</Link>
      {" · "}
      <Link href="/contact">{t.footer.contact}</Link>
    </footer>
  );
}
