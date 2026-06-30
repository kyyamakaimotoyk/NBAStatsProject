import type { Metadata } from "next";
import Link from "next/link";
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
        <header className="site-header">
          <Link href="/" className="brand">
            HoopModel
          </Link>
          <nav>
            <Link href="/">Tonight</Link>
            <Link href="/accuracy">Accuracy</Link>
            <Link href="/performance">Model</Link>
            <Link href="/explore">Explore</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
        <footer className="site-footer">
          Predictions are machine-learning model output, not betting advice.
        </footer>
      </body>
    </html>
  );
}
