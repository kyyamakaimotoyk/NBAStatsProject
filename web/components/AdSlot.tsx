"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useLang } from "@/lib/i18n";

declare global {
  interface Window {
    adsbygoogle?: object[];
  }
}

const ADSENSE_CLIENT = process.env.NEXT_PUBLIC_ADSENSE_CLIENT ?? "";

// Slot ids come from the AdSense UI after the site is approved (one display
// unit per placement). An empty id keeps that placement fully collapsed, so
// nothing renders between account approval and unit creation.
const SLOTS: Record<Placement, string> = {
  leaderboard: "",
  footer: "",
};

// No ads around the advisor's form flow. If AdSense review flags the
// market-benchmark pages, add "/accuracy" and "/performance" here.
const EXCLUDED_ROUTES = ["/advisor"];

type Placement = "leaderboard" | "footer";

export default function AdSlot({ placement }: { placement: Placement }) {
  const pathname = usePathname();
  const { t } = useLang();
  const slot = SLOTS[placement];
  const enabled =
    Boolean(ADSENSE_CLIENT && slot) &&
    !EXCLUDED_ROUTES.some((r) => pathname.startsWith(r));

  useEffect(() => {
    if (!enabled) return;
    // Rendering `enabled` ↔ null remounts the <ins> across excluded routes,
    // so this effect pushes exactly once per mounted ad element.
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch {
      // Blocked or failed loader — the fixed-height shell stays empty.
    }
  }, [enabled]);

  if (!enabled) return null;
  return (
    <div className="ad-slot">
      <span className="ad-label">{t.ads.label}</span>
      <ins
        className="adsbygoogle"
        style={{ display: "block", minHeight: 90 }}
        data-ad-client={ADSENSE_CLIENT}
        data-ad-slot={slot}
        data-ad-format="horizontal"
        data-full-width-responsive="false"
      />
    </div>
  );
}
