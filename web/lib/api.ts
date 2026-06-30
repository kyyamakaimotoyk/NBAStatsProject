// Typed client for the public predictions API. The types here mirror
// api/schemas.py exactly — if the backend contract changes, update both.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "https://api.hoopmodel.com";

export type Prediction = {
  game_id: string;
  game_date: string;
  model_type: string; // "rf" | "nn" | "xgb"
  home_team: string;
  away_team: string;
  predicted_winner: string;
  predicted_margin: number;
  home_win_probability: number; // 0..1
  margin_uncertainty: number | null;
  actual_winner: string | null;
  actual_margin: number | null;
  is_correct: boolean | null; // null until the game is played + backfilled
};

export type PredictionsResponse = {
  game_date: string | null;
  count: number;
  predictions: Prediction[];
};

export type AccuracySummary = {
  model_type: string;
  total_predictions: number;
  correct_predictions: number;
  accuracy: number | null; // 0..1
  mae: number | null;
  rmse: number | null;
  calibration_error: number | null;
};

export type AccuracySummaryResponse = {
  days: number;
  models: AccuracySummary[];
};

export type RollingPoint = {
  game_date: string;
  model_type: string;
  n_games: number;
  accuracy: number | null; // 0..1
  mae: number | null;
};

export type RollingResponse = {
  days: number;
  points: RollingPoint[];
};

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status} for ${path}`);
  return res.json() as Promise<T>;
}

export const getLatestPredictions = () =>
  getJSON<PredictionsResponse>("/api/predictions/latest");

export const getAccuracySummary = (days = 30) =>
  getJSON<AccuracySummaryResponse>(`/api/accuracy/summary?days=${days}`);

export const getRollingAccuracy = (days = 90) =>
  getJSON<RollingResponse>(`/api/accuracy/rolling?days=${days}`);

// Predicted-vs-actual rows over a window; the Model Performance page computes all
// its charts client-side from these (reuses the Prediction shape).
export type PerformanceResultsResponse = {
  days: number;
  count: number;
  results: Prediction[];
};

export const getPerformanceResults = (days = 90, model?: string) =>
  getJSON<PerformanceResultsResponse>(
    `/api/performance/results?days=${days}${model ? `&model=${model}` : ""}`,
  );
