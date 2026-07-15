# LLM Advisor Scope Expansion — Plan (2026-07-15)

Goal: the fantasy advisor should answer the questions fantasy players actually
have — trades, keepers, draft prep, week-ahead streaming, "how good is this
player" — not only start/sit questions about the current slate. Today it is
functionally "tonight only", and in the offseason effectively dead: the latest
`player_predictions` slate is from June and nothing else is in context.

Companion change (shipped 2026-07-15): the advisor now archives its responses
alongside prompts, and the local dashboard's Site Traffic tab has a
prompt/response feed. **That feed is the demand signal for this plan** — gated
and refused prompts show exactly which out-of-scope questions real users ask.

## Where the "tonight only" boundary actually lives

Nothing in the rate/cost/security layers restricts scope. The boundary is:

| Layer | File | What restricts it |
|---|---|---|
| Context | `api/advisor.py build_context()` | Only `latest_player_prediction_date()`'s slate + that date's injury report + 7-day schedule counts |
| Prompt | `api/advisor.py SYSTEM_PROMPT` | "Base every recommendation on the projection data provided … never invent projections" — the right rule, but the data block is thin, so anything off-slate gets "not in my data" |
| Gate | `api/advisor.py _topical_gate()` | Passes on the fantasy lexicon OR **current-slate** player/team names; a question naming only a non-slate player can 400 |
| Copy | `web/lib/translations.ts advisor.*` | "tonight" placeholder, `answerHeading: projection slate {d}` |

The zero-trust layers (rate gates, caps, Turnstile, refusal pinning, IAM) are
untouched by this plan.

## Phase 1 — season-wide grounding (recommended first; no model work)

Add a second, season-scoped data tier to the cached context block.

1. **New query** `api/queries.py: player_season_averages()` — per-player GP,
   MIN, PTS, REB, AST, STL, BLK, TOV, 3PM, FG%, FT% for the most recent
   season, from `boxscoretraditionalv3_player` + `game_list` (same join as
   `player_gamelog()`). Universe: players with ≥15 GP (~350 rows) to bound
   tokens. One compact line per player, same style as `_projection_block`.
2. **`build_context()` layering**:
   - Slate projections block only when fresh (`slate_date` within ~2 days of
     today); otherwise an explicit line: "No games today (off-day or
     offseason); season averages below are from the {season} season."
   - New "Season averages (actual results, not projections)" block — always.
   - Keep injury + schedule-counts blocks as-is.
   - The block must stay **byte-stable for the whole day** (it sits behind the
     Bedrock prompt-cache breakpoint) — build it once per day and cache
     in-process, like `_slate_names` does.
3. **`SYSTEM_PROMPT` rewrite**: describe the two tiers and their precedence
   (model projections for slate questions; season averages for trades,
   keepers, draft, and any player not on the slate). Keep verbatim: the pinned
   refusal sentence, the `<user_input>` anti-injection rules, "say which
   numbers drove it", "if a player is not in the data, say so".
4. **Gate expansion**: build the name-token set from the season-averages
   universe (plus team codes), not just the slate, so non-slate player names
   pass. Lexicon stays; consider adding `auction`, `adp`, `rankings`.
5. **Response semantics**: keep the `slate_date` field for compat but change
   the web heading from "projection slate: {d}" to "data as of {d}" (Phase 3).
6. **Cost check**: context grows ~+10–12k tokens, all behind the cache
   breakpoint. Worst case at the 300/day cap ≈ 6M cache-read tokens/day ≈
   low single-digit $/day at Sonnet cache-read rates — verify against current
   Bedrock pricing before shipping. Caps and `ADVISOR_MAX_TOKENS` unchanged.
7. **Verification**: `ADVISOR_DRY_RUN=1` locally (context line count sanity),
   then Bedrock smoke prompts: non-slate player question, trade question,
   offseason keeper question, and an off-topic prompt (must still refuse).

Deploy = advisor ECS service redeploy only; no schema or infra change.

## Phase 2 — week-ahead projections (season-time; decide from the feed)

- Extend `modeling/batch_predict_today.py` to also predict the next 7 days of
  scheduled games (features as-of run time), stored with future `game_date`.
  Nightly re-runs supersede stale rows — the existing
  `ROW_NUMBER() OVER (… ORDER BY prediction_timestamp DESC)` readers already
  pick the latest prediction per (game, player).
- Context gets a compact per-player aggregate ("next 7 days: 4 games, proj
  avg …"), **not** 7 raw slates — keeps the block bounded.
- Blocked until the 2026-27 schedule publishes (~August). Go/no-go: check the
  advisor feed — if week-ahead/streaming questions are common in gated or
  poorly-answered prompts, prioritize; otherwise Phase 1 may be enough.

## Phase 3 — public copy (frontend rebuild)

- `web/lib/translations.ts advisor.*` (EN + JA as transcreation, Kai owns
  terminology): subtitle and placeholder lose the "tonight" framing;
  `answerHeading` → "data as of"; disclaimer extended from "questions may be
  stored" to questions **and generated answers** may be stored (matches the
  response archiving shipped 2026-07-15).
- `web/app/advisor/page.tsx`: heading call site.

## Decisions for Kai

1. Season-block universe: ≥15 GP (~350 players, recommended) vs top-8 rotation
   only (~240, matches `player_directory()`) vs everyone (~540).
2. Offseason policy: ground keeper/draft advice in last season's averages with
   an explicit "last season's data" caveat — recommended yes; the alternative
   is keeping the advisor dark all summer.
3. Phase 2 go/no-go in August, informed by the dashboard feed.
