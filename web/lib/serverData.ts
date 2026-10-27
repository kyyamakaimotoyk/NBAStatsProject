// Build-time data for server components. With `output: "export"` these run once
// during `next build`, so whatever they return is baked into the static HTML —
// readers and crawlers see real numbers before any client fetch runs. The
// client components still refetch on mount, so a stale bake is only ever the
// first paint. A scheduled daily rebuild (frontend.yml) keeps the bake fresh.
//
// Never throws: an API outage must not fail the deploy, it just means that
// page falls back to the client-only loading path.

import {
  API_BASE,
  type AccuracySummaryResponse,
  type PlayerDailyResponse,
  type PredictionsResponse,
} from "./api";

async function buildTimeJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) {
      console.warn(`[build] ${path} → HTTP ${res.status}; page ships without baked data`);
      return null;
    }
    return (await res.json()) as T;
  } catch (e) {
    console.warn(`[build] ${path} failed (${e}); page ships without baked data`);
    return null;
  }
}

export const bakeLatestPredictions = () =>
  buildTimeJSON<PredictionsResponse>("/api/predictions/latest");

export const bakeAccuracySummary = (days: number) =>
  buildTimeJSON<AccuracySummaryResponse>(`/api/accuracy/summary?days=${days}`);

export const bakePlayerDailyLatest = () =>
  buildTimeJSON<PlayerDailyResponse>("/api/players/predictions/latest");
