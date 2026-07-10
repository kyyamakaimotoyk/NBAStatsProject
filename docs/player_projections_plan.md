# Player Counting-Stat Projections, Daily Table, and LLM Fantasy Advisor — Plan

Proposed 2026-07-09; revised 2026-07-09 after Kai's decisions. Three-part feature:
(1) per-player per-game counting-stat predictions, (2) public daily sortable projection table,
(3) LLM fantasy-lineup advisor.

Targets (per player-game): MIN (auxiliary), PTS, REB, AST, STL, BLK, TOV, 3PM, 3PA, FTM, FTA.

## Decisions (2026-07-09)

1. **FTA confirmed** as the 10th stat.
2. Feature catalog expanded (§2) — Kai to mark Tier-2 groups to include; Vegas-as-feature still open.
3. **Model plan approved:** Marcel shrinkage baseline (must-beat gate) + two-stage XGBoost
   (minutes × per-36 rates, Poisson for low-count stats; 3PM/FTM = attempts × shrunk make-rate);
   NN-embed multi-output as follow-up E-experiment.
4. **Advisor: Claude Sonnet on AWS Bedrock** with least-privilege IAM and a zero-trust protocol (§5);
   MCP tools maybe-later.
5. **Ship /players publicly**, gated on a deep calibration + validation report over the
   **last 3 seasons** (§6, "P1 report").

## 0. Data coverage (verified against DB 2026-07-09)

`boxscoretraditionalv3_player` joined to `game_list`, regular seasons:

| Season | Games | Player rows |
|---|---|---|
| 22023 (2023-24) | 1,230 | 32,385 |
| 22024 (2024-25) | 1,196 | 31,614 |
| 22025 (2025-26) | 1,221 | 31,950 |

Full regular seasons back to at least 2018-19; playoffs back to 2003. Sibling tables:
usage 38.9k games / 978k rows; playertrack 39.9k games / 1.1M rows; hustle 14.0k games
(hustle metrics only exist since ~2016 — fully covers the 3-season window).
**3-season requirement is satisfied**: ~3,647 games ≈ 96k player rows (~58k after top-8 filter).
The earlier V3-cutoff concern was ingest-behavior only, not storage. (These same numbers answer
the open 3-season-training question for the game models.)

## 1. Dataset & schema additions

- **Rows:** for each historical game, top-8 players per team by rolling MPG among available
  players (reuse `get_expected_roster` logic point-in-time). ~16 rows/game.
- **`player_features`** — keyed `(feature_set_version, GAME_ID, PERSON_ID)`, mirroring
  `core/features_io.py` (auto-evolving columns, version pointer, lineage into
  `model_registry.hyperparameters`). Separate from the game-grain `features` table.
- **`player_predictions`** — mirrors `model_predictions` conventions:
  identity (`game_id, game_date, person_id, player_name, team_id, opp_team_id, is_home`),
  `model_type, model_version`, `pred_min` + 10 `pred_*` stats, denormalized display context
  (`opp_pace_l10, opp_drtg_l10, team_pace_l10, opp_3pa_allowed_l10`), `actual_*` + per-stat
  errors (graded nightly, `backfill_actuals` style), `prediction_timestamp`,
  `UNIQUE (game_id, person_id, model_type, model_version)` upsert.

## 2. Feature catalog (expanded)

All rolling features leakage-safe `shift(1)` L5/L10, matching `calculate_rolling_features`.
Tiers: **T1** = v1 model; **T2** = candidate, added in group-wise ablation batches under the
e3 multi-seed + paired-test protocol; **T3** = only if a specific stat lags; skip = data absent.

### A. Player form & volume (traditional / advanced / usage / scoring player tables)
| Feature | Drives | Tier |
|---|---|---|
| MIN_L5/L10 mean, MIN_STD_L10, MIN trend (L5−L10) | minutes | T1 |
| Each target stat L5/L10, per-game and per-36 | all | T1 |
| Season-to-date per-36 + games played (shrinkage prior) | all | T1 |
| Prior-season per-36, blend weight by current-season GP (early-season prior) | all | T1 |
| USG% L5/L10 | volume | T1 |
| TS% / eFG% L10 | PTS, 3PM, FTM | T1 |
| 3PAr (3PA/FGA) and FTr (FTA/FGA) L10 — shot diet | 3PA, FTA | T1 |
| Individual OREB% / DREB% / AST% / TOV-ratio L10 | REB, AST, TOV | T1 |
| Starts share L10 (starter flag) | minutes | T1 |
| DNP count L10; games since return from ≥2-week absence (minutes ramp) | minutes | T1 |
| PIE L10 | overall | T2 |
| Home/away per-36 splits (season) | all | T2 |
| % points assisted/unassisted; points share from 3 / FT / paint (scoring table) | shot profile | T2 |

### B. Opportunity & role (playertrack / hustle / misc player tables)
| Feature | Drives | Tier |
|---|---|---|
| Touches and passes-made per game L10 (playertrack) | AST | T2 |
| Rebound chances per game L10 (playertrack) — opportunity vs conversion | REB | T2 |
| Contested shots, deflections, loose balls L10 (hustle) | STL, BLK | T2 |
| Second-chance / fastbreak / paint points L10 (misc) | PTS composition | T2 |
| Screen assists, box outs L10 (hustle) | role, REB | T3 |
| Speed / distance per game (playertrack) — fatigue proxy | minutes | T3 |

### C. Teammate context — the usage vacuum
| Feature | Drives | Tier |
|---|---|---|
| PLAYERS_OUT, TOTAL_MISSING_IMPACT (existing) | usage bump | T1 |
| Vacated USG% = Σ usage of OUT teammates (new; player_impact × injuries) | volume | T1 |
| Vacated minutes at same position | minutes | T2 |
| ROSTER_DEPTH_SCORE, STAR_PLAYER_IMPACT, TOP_3_SCORER_SHARE (existing) | context | T2 |

### D. Schedule & fatigue (mostly existing team machinery)
| Feature | Drives | Tier |
|---|---|---|
| Player rest days; team B2B / 3-in-4 / games-last-7 / road-trip length; HOME | minutes, all | T1 |
| Minutes in previous game; cumulative MIN last 3 (heavy-leg effect) | minutes | T2 |
| Travel distance / time zones | — | skip (not ingested) |

### E. Own-team environment
| Feature | Drives | Tier |
|---|---|---|
| TEAM_PACE_L10 | volume | T1 |
| TEAM_OREB%/DREB%, AST%, TOV%, 3PA rate, FT rate L10 | matching stats | T1 |
| Team ELO and ELO diff (strength → blowout risk) | minutes | T2 |
| LINEUP_ snapshots (E11) | — | T3 (no effect at team level in E3) |

### F. Opponent defense
| Feature | Drives | Tier |
|---|---|---|
| OPP_PACE_L10 (+ EXPECTED_POSS = mean of both paces) | all volume | T1 |
| OPP_DEF_RATING_L10 | PTS, 3PM, FTM | T1 |
| OPP_DREB_PCT_L10 / OPP_OREB_PCT_L10 | OREB / DREB | T1 |
| OPP_EFG_PCT_L10 (their own offense — misses create DREB chances) | REB | T1 |
| OPP_3PA_RATE_ALLOWED_L10, OPP_3P_PCT_ALLOWED_L10 | 3PA, 3PM | T1 |
| OPP_FT_RATE_ALLOWED_L10 (or PF per game) | FTA, FTM | T1 |
| OPP_TOV_PCT_L10 (giveaways) / OPP_TOV_FORCED_L10 | STL / TOV | T1 |
| OPP_PITP_L10 (their rim pressure) | BLK | T1 |
| Allowed counting stats per game (REB/AST/STL/BLK/3PM allowed L10 — reuse E10 `_ALLOWED_L10` machinery) | direct matchup | T2 |
| Opponent DFG% / rim-defended shots (boxscoredefensivev2 — verify pregame availability + coverage) | BLK, PTS | T2 |
| Opponent hustle: deflections, contested shots L10 | STL, TOV | T2 |
| Position-vs-defense (pts allowed to G/W/B) | all | T3 (position field patchy) |
| Individual matchup histories (defensive v2 matchups) | — | skip (sparse, not knowable pregame) |

### G. Market / game environment (pending Kai's call on market data as input)
| Feature | Drives | Tier |
|---|---|---|
| \|home_spread\| — blowout risk | minutes | T2 |
| Game total | environment | T2 |
| Team implied total (total/2 ∓ spread/2) — best single scoring-environment signal | PTS et al. | T2 |

### H. Engineered interactions
| Feature | Tier |
|---|---|
| EXPECTED_POSS × player USG% → expected opportunities | T1 (derived) |
| Matchup products, e.g. player 3PA/36 × opp 3PA-rate-allowed ratio (same for FTA, REB) | T2 |
| Minutes × rate — encoded structurally by the two-stage model | — |

Not available (skip): referee assignments, player prop lines, player age/DOB, venue/altitude
beyond HOME, on/off splits beyond E11 snapshots.

Rollout: T1 → v1. T2 → grouped ablations (A2/B/C2/F2/G batches), keep only what survives
multi-seed paired tests. E10's team-level MAE regression is a standing caution for group F T2.

## 3. ML models (approved)

- **C. Baseline (build first): Marcel-style shrinkage** — weighted L5/L10/season per-36 blend
  regressed to position mean × projected minutes. The must-beat gate.
- **A. Production: two-stage XGBoost** — minutes regressor + per-36 per-stat rate models
  (Poisson `count:poisson` for STL/BLK/TOV/3PM; squared error for PTS/REB/AST). Predict 3PA/FTA
  volume; derive 3PM = 3PA × shrunk season 3P%, FTM = FTA × shrunk FT% (coherence: makes ≤
  attempts). Registry/bundles/S3/leakage-guard via the `model_types.py` recipe. Conformal
  intervals via existing `ConformalRegressor`.
- **B. Follow-up E-experiment: multi-output PyTorch MLP + player embeddings** (shared trunk,
  11 heads; reuse nn-embed `nn.Embedding` + `create_player_id_mapping`). Judge vs A with the
  e3 harness.
- **D. Later:** distributional outputs (quantile XGB / NGBoost) for P(stat ≥ x).

## 4. Daily sortable table (web) — ships publicly after the P1 gate

Injury-report full-stack template (commit `7614d68`):
`api/queries.py` + `api/schemas.py` + `GET /api/players/predictions?date=|latest` →
`web/lib/api.ts` → new `web/components/PlayerProjectionsTable.tsx` (**first click-to-sort
table in the repo**: sortKey/sortDir state, `aria-sort`, numeric compare, `.results-scroll`
sticky header, `.pred-table` styles) → `web/app/players/page.tsx` (+ metadata split as in
`/about`) → nav link + `translations.ts` en/ja (transcreation) → CloudFront 5-min cache
behavior for `/api/players/*`.
Columns: player, team, opp + context (opp pace/DRtg/3PA-allowed L10, own pace L10), MIN + 10
stats. Controls: date picker, team filter.

## 5. LLM advisor — Claude Sonnet on AWS Bedrock, zero-trust

**Model/client:** `AnthropicBedrockMantle(aws_region=...)` from `anthropic[bedrock]`
(pure Python — API image stays slim), model **`anthropic.claude-sonnet-5`**. Auth is SigV4
from the Fargate task role — **no API key, no new secret, nothing to rotate or leak.**
Bedrock notes: prompt caching supported via explicit `cache_control` blocks (top-level
automatic caching is not); server-side MCP connector is NOT available on Bedrock — any future
tools run as our own server-side tool loop (which fits zero-trust better anyway); Sonnet 5
rejects non-default temperature/top_p/top_k; forced `tool_choice` on Bedrock requires thinking
disabled (irrelevant until tools). One console step for Kai: enable Anthropic model access in
Bedrock for the account/region.

**Endpoint:** `POST /api/advisor` `{prompt, roster?, matchup_score?, scoring_type?}` on the
FastAPI service. Server fetches context itself: today's `player_predictions`, injuries,
games-per-team next 7 days (`league_schedule` — the streaming-pickup signal). Single
`messages.create`, `max_tokens` ≈ 1,500, non-streaming v1. Request shape: stable system
prompt → day's projection table with `cache_control: {"type": "ephemeral"}` → delimited user
content (volatile) after the breakpoint.

**Zero-trust protocol:**
1. **Model holds nothing.** No credentials, no DB access, no tools (v1). Context is fetched
   by the server with the existing read-only DB user and injected as text.
2. **Least-privilege IAM.** Task role gains exactly `bedrock:InvokeModel` on the one Sonnet
   model/inference-profile ARN. No other permission changes.
3. **User input is untrusted.** Body-size + field-length caps (~4k chars), charset validation,
   wrapped in delimiters, system prompt instructs the model to treat delimited content as data
   (prompt-injection hardening). User text never touches SQL (context queries take no user
   parameters beyond a validated date).
4. **Model output is untrusted.** Rendered as sanitized text/markdown in React (no
   `dangerouslySetInnerHTML`), never parsed into actions, never fed into queries.
5. **Transport gates.** POST allowed only for `/api/advisor` (CORS adds POST; CloudFront gets
   a dedicated behavior with full-methods + CachingDisabled — all other paths stay GET-only);
   per-IP token-bucket rate limit in-app (WAF later); global daily request cap +
   kill-switch env var; `max_tokens` cap.
6. **Observability.** CloudWatch metrics (requests, tokens, latency), AWS billing alarm on
   Bedrock spend; log request metadata, not full prompts.
7. **MCP tools: deferred.** V1 is context-stuffing (table fits trivially in context). If added
   later: server-side tool loop with read-only, allowlist-validated functions
   (`get_player_projection`, `get_team_schedule`); the model still never touches the DB.

Cost @ ~6k in / 800 out per request on Sonnet 5 ($3/$15 per MTok; intro $2/$10 through
2026-08-31): ≈ **$0.02–0.03/request**, less with warm cache.

**UI:** `/advisor` page or panel on `/players`: textarea + scoring-type select → POST →
render advice. EN/JA.

## 6. P1 validation & calibration report (the /players gate)

Data: regular seasons 2023-24, 2024-25, 2025-26 (~96k player rows; ~58k after top-8 filter);
optionally + playoffs.
Protocol: walk-forward — train 23-24 → validate 24-25; train 23-24+24-25 → validate 25-26 —
plus within-season temporal 80/20 for the production candidate. Rolling windows warm up on the
prior season's tail. Baselines: naive L10 average and Marcel; paired significance
(paired-t / bootstrap on per-row |error|) per `feedback_noise_aware_eval`.

Report contents, per stat:
- **Accuracy:** MAE, RMSE, bias (mean signed error), R²; skill % vs Marcel.
- **Calibration:** decile reliability curves (mean predicted vs mean actual per predicted
  decile); for Poisson stats (STL/BLK/TOV/3PM) predicted vs empirical frequency of 0/1/2/3+;
  conformal 80/90% interval coverage (nominal vs empirical).
- **Minutes decomposition:** re-score rate models with *actual* minutes to attribute error to
  minutes-model vs rate-model; minutes MAE + calibration reported separately.
- **Slices:** starter vs bench, projected-minutes buckets, B2B vs rested, home/away, month,
  teammate-out vs full-strength games.
- **Fantasy aggregates:** points-league MAE and 9-cat z-score MAE.

Artifacts (e-series conventions): `outputs/p1_player_validation.json` +
`docs/p1_player_validation_report.md`; charts as straight lines with visible points.
**Gate: /players ships only after Kai reviews P1.**

## 7. Phasing

- **Phase A — dataset + models + P1 report.** Dataset builder (3 seasons) → Marcel baseline →
  two-stage XGBoost → P1 report. *Gate: Kai reviews P1.*
- **Phase B — production plumbing.** `player_predictions` table, nightly batch (top-8 via
  `get_expected_roster` + live injuries), grading job, pipeline stages (`player_features`,
  `player_train`), registry/bundle wiring.
- **Phase C — /players page** (§4), public at launch.
  - **C-partial DONE 2026-07-09 — player-explore page** (Kai request): `player_predictions`
    table created + backfilled with P1 walk-forward out-of-sample predictions
    (`scripts/backfill_player_predictions.py`, 38,177 rows, 2024-25 + 2025-26; 2023-24 is
    training-only so has none). New API endpoints `/api/players/directory|gamelog|team-context`
    (public-safe; gamelog = 3 seasons of actuals LEFT JOIN predictions, DNP rows excluded;
    team-context = L10 profile + next opponent from `league_schedule`, gracefully null in
    the offseason). New page `/players/explore`: team→player→stat→window dropdowns,
    actual-vs-predicted game chart (tooltip: date, opponent, pred, actual), stat distribution
    with Poisson overlay for STL/BLK/TOV/3PM, prediction-error histogram with MAE/bias,
    team-vs-next-opponent panel. EN/JA copy; nav "Players".
    **Prod deploy step**: RDS has no `player_predictions` rows until
    `python scripts/backfill_player_predictions.py` runs against RDS (one-off pipeline-task
    run, same env as the nightly job) — until then the page shows the empty state.
- **Phase D — advisor** (§5): IAM + Bedrock access, endpoint, guardrails, UI.
- **Phase E (optional/parked):** NN-embed experiment (B), distributional outputs (D), MCP
  tool loop, Tier-2 feature ablation rounds.

Timing: offseason now — A/B on historical data; nightly output live from October tip-off.

## Open items — RESOLVED 2026-07-09

1. Tier-2 groups for round 1: **A, B, C, G** (Kai). D2/E2/F2/H2 stay parked for a later
   ablation round. A correlation matrix (feature x target + feature x feature) ships with
   the P1 report.
2. Vegas/market data as model input: **YES** (group G in v1).
3. Bedrock region: **us-east-1**. Advisor isolation: Kai leans **separate role** — note
   one IAM task role per ECS task, so "separate role" in practice means a separate
   `advisor` ECS service (own task def/role/target group + CloudFront path routing for
   `/api/advisor*`). Trade-off vs. extending the API task role with a scoped
   `bedrock:InvokeModel` policy: full blast-radius isolation + independent kill switch
   + clean cost attribution, at ~$9-10/mo for a second always-on 0.25vCPU Fargate task
   and a bit more Terraform. Implement in Phase D.

Learning track: `docs/bedrock_lab.md` (hands-on Bedrock/LLM labs, Kai-executed)
accompanies Phase D.
