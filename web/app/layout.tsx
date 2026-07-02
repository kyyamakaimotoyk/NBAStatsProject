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
            <Link href="/accuracy">Track record</Link>
            <Link href="/performance">Model lab</Link>
            <Link href="/explore">Explore</Link>
            <Link href="/scatter">Scatter</Link>
            <Link href="/drivers">What wins games</Link>
            <Link href="/about">About</Link>
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
