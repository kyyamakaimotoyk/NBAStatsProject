import type { Metadata } from "next";
import { LanguageProvider } from "@/lib/i18n";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import AdSlot from "@/components/AdSlot";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://hoopmodel.com"),
  // Child pages set a short title ("Track record") and get the suffix; the
  // home page uses the default. Distinct per-page titles matter to search and
  // to ad-network site review, which reads them as distinct content.
  title: {
    default: "HoopModel — NBA game predictions",
    template: "%s — HoopModel",
  },
  description:
    "Nightly machine-learning predictions for NBA games, with historical accuracy.",
  openGraph: { siteName: "HoopModel", type: "website" },
};

// Both ids are injected at build time in .github/workflows/frontend.yml.
// Unset (local dev, or before the accounts exist) → no third-party scripts,
// no ad slots — the site renders exactly as it did before monetization.
const GA_ID = process.env.NEXT_PUBLIC_GA_ID ?? "";
const ADSENSE_CLIENT = process.env.NEXT_PUBLIC_ADSENSE_CLIENT ?? "";

// Consent Mode v2: storage starts denied where consent is legally required
// (EEA + UK + Switzerland + Canada — Google mandates a certified consent
// message for all four); granted elsewhere (US has no opt-in requirement).
// Google's Privacy & messaging CMP, loaded with the AdSense script, shows the
// banner in those regions and updates these defaults. wait_for_update holds
// tags briefly so the CMP's stored choice applies before anything fires.
const CONSENT_REGIONS =
  "AT,BE,BG,HR,CY,CZ,DK,EE,FI,FR,DE,GR,HU,IE,IT,LV,LT,LU,MT,NL,PL,PT,RO,SK,SI,ES,SE,IS,LI,NO,GB,CH,CA";

const consentAndGaBootstrap = `
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('consent', 'default', {
  ad_storage: 'denied',
  ad_user_data: 'denied',
  ad_personalization: 'denied',
  analytics_storage: 'denied',
  region: '${CONSENT_REGIONS}'.split(','),
  wait_for_update: 2000
});
gtag('consent', 'default', {
  ad_storage: 'granted',
  ad_user_data: 'granted',
  ad_personalization: 'granted',
  analytics_storage: 'granted'
});
${GA_ID ? `gtag('js', new Date());\ngtag('config', '${GA_ID}');` : ""}
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const monetized = Boolean(GA_ID || ADSENSE_CLIENT);
  return (
    <html lang="en">
      <body>
        {monetized && (
          // Plain script tags, not next/script: they must land verbatim in the
          // static export, and the inline consent default has to execute
          // before the async gtag/adsbygoogle loaders process anything.
          <>
            <script dangerouslySetInnerHTML={{ __html: consentAndGaBootstrap }} />
            {GA_ID && (
              <script
                async
                src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
              />
            )}
            {ADSENSE_CLIENT && (
              <script
                async
                src={`https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}`}
                crossOrigin="anonymous"
              />
            )}
          </>
        )}
        <LanguageProvider>
          <SiteHeader />
          <AdSlot placement="leaderboard" />
          <main className="container">{children}</main>
          <AdSlot placement="footer" />
          <SiteFooter />
        </LanguageProvider>
      </body>
    </html>
  );
}
