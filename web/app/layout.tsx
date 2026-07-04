import type { Metadata } from "next";
import { LanguageProvider } from "@/lib/i18n";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import "./globals.css";

export const metadata: Metadata = {
  title: "HoopModel — NBA game predictions",
  description:
    "Nightly machine-learning predictions for NBA games, with historical accuracy.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <LanguageProvider>
          <SiteHeader />
          <main className="container">{children}</main>
          <SiteFooter />
        </LanguageProvider>
      </body>
    </html>
  );
}
