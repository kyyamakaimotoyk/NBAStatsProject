import type { MetadataRoute } from "next";

// Emitted as /sitemap.xml by the static export. Every public page, nothing
// else; the advisor is included because its page carries real prose even
// though the answers are generated per request.
export const dynamic = "force-static";

const BASE = "https://hoopmodel.com";

const PAGES: { path: string; changeFrequency: "daily" | "weekly" | "monthly"; priority: number }[] = [
  { path: "/", changeFrequency: "daily", priority: 1.0 },
  { path: "/accuracy/", changeFrequency: "daily", priority: 0.9 },
  { path: "/players/", changeFrequency: "daily", priority: 0.8 },
  { path: "/performance/", changeFrequency: "daily", priority: 0.7 },
  { path: "/players/explore/", changeFrequency: "daily", priority: 0.6 },
  { path: "/explore/", changeFrequency: "weekly", priority: 0.6 },
  { path: "/scatter/", changeFrequency: "weekly", priority: 0.5 },
  { path: "/drivers/", changeFrequency: "weekly", priority: 0.5 },
  { path: "/advisor/", changeFrequency: "monthly", priority: 0.5 },
  { path: "/about/", changeFrequency: "monthly", priority: 0.6 },
  { path: "/contact/", changeFrequency: "monthly", priority: 0.3 },
  { path: "/privacy/", changeFrequency: "monthly", priority: 0.3 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return PAGES.map(({ path, changeFrequency, priority }) => ({
    url: `${BASE}${path}`,
    lastModified,
    changeFrequency,
    priority,
  }));
}
