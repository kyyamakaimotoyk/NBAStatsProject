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
  // Market closing line's implied home margin (benchmark, not model output).
  // Only /api/performance/results populates it; null elsewhere.
  market_margin?: number | null;
  // Final score from game_list (null until the game is final).
  home_score?: number | null;
  away_score?: number | null;
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

// Rolling-feature time series for the data-exploration page.
export type FeatureTimeseriesRow = {
  game_date: string;
  home_team: string | null;
  away_team: string | null;
  home_value: number | null;
  away_value: number | null;
};

export type FeatureTimeseriesResponse = {
  feature: string;
  window: string;
  days: number;
  count: number;
  rows: FeatureTimeseriesRow[];
};

export const getFeatureTimeseries = (feature: string, window: "L5" | "L10", days = 365) =>
  getJSON<FeatureTimeseriesResponse>(
    `/api/explore/feature?feature=${encodeURIComponent(feature)}&window=${window}&days=${days}`,
  );

// Per-team-game scatter points for two chosen stats.
export type ScatterPoint = {
  game_date: string;
  team: string | null;
  wl: string | null;
  x: number | null;
  y: number | null;
  home_team: string | null; // abbreviations (e.g. "LAL"), derived from MATCHUP
  away_team: string | null;
  winner: string | null;
};

export type ScatterResponse = {
  x: string;
  y: string;
  days: number;
  count: number;
  points: ScatterPoint[];
};

export const getScatter = (x: string, y: string, days = 365) =>
  getJSON<ScatterResponse>(
    `/api/explore/scatter?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}&days=${days}`,
  );

// Pre-game injury report for one date (NBA-published, public info).
export type InjuryItem = {
  team_name: string;
  player_name: string;
  status: string;
  reason: string | null;
};

export type InjuryReportResponse = {
  game_date: string;
  count: number;
  injuries: InjuryItem[];
};

export const getInjuryReport = (date: string) =>
  getJSON<InjuryReportResponse>(`/api/explore/injuries?date=${encodeURIComponent(date)}`);

// Features ranked by correlation with winning margin.
export type MarginCorrItem = { feature: string; column: string; correlation: number };

export type MarginCorrResponse = {
  kind: string;
  window: string;
  count: number;
  correlations: MarginCorrItem[];
};

export const getMarginCorrelations = (kind: "DIFF" | "HOME" | "AWAY", window: "L5" | "L10") =>
  getJSON<MarginCorrResponse>(`/api/explore/margin-corr?kind=${kind}&window=${window}`);

// --- Player explore -----------------------------------------------------------

export type PlayerDirEntry = {
  person_id: number;
  player_name: string | null;
  team_id: number | null;
  team_abbrev: string | null;
};

export type PlayerDirectoryResponse = {
  count: number;
  players: PlayerDirEntry[];
};

// One played game: actual counting stats + the model's out-of-sample prediction
// where one exists (pred_* are null for games the projection model didn't cover).
export type PlayerGameRow = {
  game_date: string;
  opp: string | null;
  is_home: number;
  min: number | null;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  stl: number | null;
  blk: number | null;
  tov: number | null;
  fg3m: number | null;
  fg3a: number | null;
  ftm: number | null;
  fta: number | null;
  pred_min: number | null;
  pred_pts: number | null;
  pred_reb: number | null;
  pred_ast: number | null;
  pred_stl: number | null;
  pred_blk: number | null;
  pred_tov: number | null;
  pred_fg3m: number | null;
  pred_fg3a: number | null;
  pred_ftm: number | null;
  pred_fta: number | null;
};

export type PlayerGamelogResponse = {
  person_id: number;
  player_name: string | null;
  count: number;
  rows: PlayerGameRow[];
};

export type TeamProfile = {
  team_id: number;
  team_abbrev: string | null;
  pace: number | null;
  off_rtg: number | null;
  def_rtg: number | null;
  oreb_pct: number | null;
  dreb_pct: number | null;
  efg_pct: number | null;
  ast_pct: number | null;
  fg3a_pg: number | null;
  fta_pg: number | null;
  pts_pg: number | null;
};

export type NextGameInfo = {
  game_date: string;
  is_home: boolean;
  opp_team_id: number;
  opp_abbrev: string | null;
};

export type TeamContextResponse = {
  team: TeamProfile;
  next_game: NextGameInfo | null; // null in the offseason
  opponent: TeamProfile | null;
};

export const getPlayerDirectory = () =>
  getJSON<PlayerDirectoryResponse>("/api/players/directory");

export const getPlayerGamelog = (personId: number) =>
  getJSON<PlayerGamelogResponse>(`/api/players/gamelog?person_id=${personId}`);

export const getTeamContext = (teamId: number) =>
  getJSON<TeamContextResponse>(`/api/players/team-context?team_id=${teamId}`);

// --- Daily projections table ---------------------------------------------------

// One player's projection for one game, with own/opponent L10 context and
// actuals once graded (null until then).
export type PlayerDailyRow = {
  game_date: string;
  person_id: number;
  player_name: string | null;
  team_abbrev: string | null;
  opp_abbrev: string | null;
  is_home: number;
  team_pace_l10: number | null;
  opp_pace_l10: number | null;
  opp_drtg_l10: number | null;
  opp_3pa_allowed_l10: number | null;
  pred_min: number | null;
  pred_pts: number | null;
  pred_reb: number | null;
  pred_ast: number | null;
  pred_stl: number | null;
  pred_blk: number | null;
  pred_tov: number | null;
  pred_fg3m: number | null;
  pred_fg3a: number | null;
  pred_ftm: number | null;
  pred_fta: number | null;
  actual_min: number | null;
  actual_pts: number | null;
  actual_reb: number | null;
  actual_ast: number | null;
  actual_stl: number | null;
  actual_blk: number | null;
  actual_tov: number | null;
  actual_fg3m: number | null;
  actual_fg3a: number | null;
  actual_ftm: number | null;
  actual_fta: number | null;
};

export type PlayerDailyResponse = {
  game_date: string | null;
  count: number;
  rows: PlayerDailyRow[];
};

export const getPlayerDailyLatest = () =>
  getJSON<PlayerDailyResponse>("/api/players/predictions/latest");

export const getPlayerDaily = (date: string) =>
  getJSON<PlayerDailyResponse>(`/api/players/predictions?date=${date}`);
