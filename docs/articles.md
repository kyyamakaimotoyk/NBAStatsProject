# Articles: ideas and publication log

*Started 2026-10-27. Tracks every article idea for the `/articles` section of
hoopmodel.com: what it would say, which report it draws on, and whether it's
published. Ideas came from a pass over every report in `docs/`.*

Why this section exists: AdSense rejected the site for low-value content
(see `docs/ad_monetization_plan.md`). Original written analysis is the strongest
fix, and the experiment reports are full of findings that are interesting to a
general basketball audience.

## How to publish one

1. Write the body in `web/components/articles/<Name>.tsx` as two named
   exports, `<Name>En` and `<Name>Ja` (plain JSX prose; `Link` for internal
   links).
2. Add the metadata entry (slug, date, read time, EN/JA title + summary,
   `hasJapanese`) to the top of `ARTICLES` in `web/lib/articles.ts`.
3. Register `{ en, ja }` in `BODIES` in `web/app/articles/[slug]/page.tsx`.
   The index page, per-article metadata and sitemap pick it up automatically.
4. Build the figures (see the figures rule below): add a builder function for
   the slug to `scripts/build_article_figures.py`, run
   `python scripts/build_article_figures.py <slug>`, write
   `web/components/articles/figures/<Name>Figures.tsx`, and place the figures
   in both the EN and JA bodies.
5. Recompute any live numbers from the API right before publishing (the
   builder does this for API-backed articles). Never copy stale figures from
   an old report when a current one exists. Then re-read the text against the
   generated JSON: every number in the prose must match a figure.
6. Update the status in the table below.

## Disclosure line (applies to every article)

OK to publish: questions, methods (paired tests, walk-forward validation,
conformal intervals), verdicts, effect sizes, public baselines (Elo, Marcel,
the betting market), public data sources.

Not OK: exact feature lists or feature counts, hyperparameter values, how the
injury/availability features are built, data-pipeline internals, code, and
anything that would let someone rebuild the production feature set. When a
finding is only interesting *because* of a specific production feature, mark it
**Hold** instead of publishing a vague version.

## Figures rule (applies to every article)

*Set by Kai 2026-10-30.* If we have data, we show it. An article that argues
from numbers must let the reader see those numbers, not just read about them.

- **At least one figure per article; usually two or three.** Every comparison,
  distribution, trend or effect size the argument rests on gets a figure. A
  single number the sentence already states completely doesn't need one.
- **Real data only.** Figures are built by `scripts/build_article_figures.py`
  from experiment outputs (`outputs/*.json`), the features snapshot, or the
  live API, into `web/data/articles/<slug>.json`. No hand-typed or
  illustrative numbers. If a result only exists as a number in the tuning log,
  re-run or export it first; if that isn't possible, chart the logged numbers
  and say so in the source line.
- **Text and figures agree.** Prose numbers come from the same JSON. Re-run
  the builder and re-check the text before publishing or refreshing. (Drawing
  the figures for #1-#4 caught two text errors: #2 compared models and market
  on different game sets, and #1 said "9 of 11 improved, one exception" when
  turnovers also improved without clearing the bar.)
- **Show the uncertainty** when the argument is about noise or a null result:
  ranges or confidence intervals (`RangeChart`), not bare means.
- **Every figure goes through `<Figure>`**: numbered title, a caption that tells
  the reader what to notice, a source line (what data, how many games/seeds,
  which dates), and a "Show the data" table. The table and caption are
  server-rendered, so the numbers are in the prerendered HTML for crawlers.
- **Chart style**: the primitives in `web/components/articles/figures/charts.tsx`
  (`RangeChart`, `Bars`, `Lines`) in the site's dark chart style, with
  zero-based bars, straight lines with visible points, and model colors from
  `colors.ts`. Models are always named on an axis or in a legend, never by
  color alone: NN green and XGB amber fail the colorblind-separation check.
- **Both languages**: titles, captions, axis labels and source lines in EN and
  JA, held to the same transcreation standard as the prose. Stat keys (PTS,
  REB, ...) stay untranslated.
- **The disclosure line applies to figures too.** The data JSON ships in the
  public bundle, so the builder writes aggregates only: no feature names on
  axes, no feature counts, no hyperparameters, and no importance rankings.
- **When an article is about a system rather than a dataset** (e.g. #18), the
  figure is a diagram of the mechanism.

## Status key

- **Published**: live on the site (date = publication date)
- **Ready**: findings are final and safe to publish; just needs writing
- **Blocked**: the underlying question is still open
- **Hold**: disclosure concern; publish only if reframed or approved by Kai

## Summary table

| # | Working title | Source(s) | Status |
|---|---|---|---|
| 1 | Signal or noise? How we decide whether a model change is real | tuning log E12, E24, P7/P7b; `e3_ablation_report.md` | **Published** 2026-10-27 (EN + JA); figures 2026-10-30 |
| 2 | Why nobody predicts NBA margins within five points | `post_e11_synthesis.md` + live API numbers | **Published** 2026-10-27 (EN + JA); figures 2026-10-30 |
| 3 | Last season's impact ratings don't help predict this season | `p3_impact_metrics_report.md`, tuning log E25, assessment §5 | **Published** 2026-10-27 (EN + JA); figures 2026-10-30 |
| 4 | Playoff games are harder to predict, and it's not the model's fault | `e15_cross_context_report.md` (Q2) | **Published** 2026-10-27 (EN + JA); figures 2026-10-30 |
| 5 | What does "70% confident" actually mean? | `e13_calibration_report.md`, tuning log E19–E21 | Ready |
| 6 | More data didn't help: how much history a model needs | `e15_cross_context_report.md` (Q1), tuning log E2/E3 | Ready (timely: early season) |
| 7 | Even the betting market can't call the playoffs | tuning log E16/E17, `playoff_improvement_plan.md` | Ready |
| 8 | Most of a player's scoring swing is luck | `p1_`/`p2_player_validation_report.md`, assessment §3.1 | Ready |
| 9 | Beating a dumb-but-strong baseline (Marcel) | `p1_player_validation_report.md` | Ready |
| 10 | Why steals and blocks are counted, not measured | P1/P2 reports (Poisson), tuning log P5 | Ready |
| 11 | Is the random forest really the worst model? | assessment §2.3, tuning log E1/E21 | Ready |
| 12 | Leakage: how a model can cheat without anyone noticing | tuning log E7, E18 | Hold (availability design) |
| 13 | Fewer features, better model | tuning log E22, assessment §2.1 | Ready (with care) |
| 14 | 99.9% training accuracy: what overfitting looks like | tuning log E1 | Ready |
| 15 | The bug that made our neural net look broken | tuning log E8, E6 | Ready |
| 16 | Why the models sometimes disagree with themselves | memory/`project_head_disagreement`, `PredictionsTable.tsx` "split" badge | Blocked (root cause open) |
| 17 | What helped player minutes (and what hurt turnovers) | tuning log P4 | Hold (reveals adopted features) |
| 18 | How a static website grades itself every night | `aws_deployment_plan.md`, ops labs | Ready (no security details) |
| 19 | Most of our traffic isn't human | `traffic_lab.md` | Idea (check numbers) |
| 20 | Monthly check-in: how the models are doing this season | live API | Recurring (first: late Nov 2026) |
| 21 | Japanese versions of #1–#4 | — | **Done** 2026-10-27 |

## Published

### 1. Signal or noise?
`/articles/signal-or-noise/`. A 230-game test month makes accuracy wobble ±5pp
from seeds and game draw alone; paired tests (McNemar, paired t, bootstrap of the
AUC difference) are what separate signal from that. Elo kept; lineup stats
(the "+2.6pp" result) and opponent-adjusted stats dropped. Team tuning search
didn't transfer to held-out data (7–7 on disagreements); player tuning did (9/11
stats), with blocks kept on original settings. Ends with the working rules.

**Figures (2026-10-30):** (1) winner accuracy with 95% ranges for
baseline / +Elo / +opponent-adjusted / +lineups x RF/XGB (`e3_ablation_e7on.json`);
(2) game-by-game disagreement splits, incl. the tuning 7-7 (`e3` paired,
`e24_w5.json`); (3) player-tuning % change in MAE per stat (`p7_gate.json`).
Text fixed: 9/11 cleared the bar, turnovers improved without clearing it.

### 2. Why nobody predicts NBA margins within five points
`/articles/margin-floor/`. Live numbers (2026-10-27, 4,203 games): margin SD
≈16, median game decided by 10, constant "home by 2" guess misses by 12.7,
models ≈11.5, closing line 10.8, only 31% of games within 5 of the line; model
error p50 9.5 / p80 18.7. Explains shooting variance, game state, late info.
**Refresh these numbers each season.**

**Figures (2026-10-30, live API, 4,208 games):** (1) histogram of final margins,
1-point bins; (2) average miss by predictor (naive "home by 2", RF, NN, XGB,
market) on the **same** 3,642 games with a closing line; (3) share of games
within X points of the prediction, market vs models. Text updated to the
same-games numbers: models ~11.7 (was 11.5 over all games), naive 12.8 (was
12.7); market 10.8 and 31% within 5 unchanged.

### 3. Last season's impact ratings don't help predict this season
`/articles/impact-ratings/`. Player model: 0/11 stats pass, biggest ΔMAE −0.007,
features used but redundant. Team model: standalone r = 0.28 and 65% home-win
when positive, but null in-model, null pooled over 21 windows, slightly worse
Oct–Dec. Open item: daily-updated ratings untested. **Judgment call flagged to
Kai:** the article describes the rejected experiment's roster construction
(recent appearances minus Out/Doubtful); cut if too close to the line.

**Figures (2026-10-30):** (1) player model % change in MAE per stat with
best/worst run (`p3_impact_metrics.json`); (2) home win rate by rating-gap
quintile, 39% -> 71% (`e25_eraptor_team_cols.csv` + frozen snapshot); (3) team
model dAUC with 95% CI, held-out month and 21-month pool (`e25_w5.json`,
`e25_windows.json`). Strong alone, nothing added: the article's point in two charts.

### 4. Playoff games are harder to predict
`/articles/playoff-predictability/`. Five seasons, ~630 control / ~400 playoff
games. Accuracy 71→64% (RF), 69→62% (XGB); AUC ~0.79→0.60–0.64; 90% margin
ranges still cover 88–90%, MAE 11.9→12.1. Causes: compressed strength gap,
slower pace, series adjustments. Play-in n=30, no claim.

**Figures (2026-10-30):** (1) small multiples, late regular season vs playoffs:
accuracy, AUC, 90%-range coverage (`e15_regime.json`); (2) distribution of the
Elo favorite's pre-game win probability, last three regular-season weeks vs
playoffs (frozen snapshot): favorites above 80% fall from 25% of games to 9%.

## Ready to write

### 5. What does "70% confident" actually mean?
The calibration story, which has an unusually good honest-failure arc.
- Start with the RF finding: games it called 70% won ~87%. Underconfident, so
  isotonic recalibration was added (E13). Include the "confident misses get
  worse" caveat from the report (Brier example).
- Then the twist (E19): live, a stale calibrator pushed ~97% of RF picks to the
  home team and flipped correct picks; live RF accuracy 58% vs 74% in testing.
- Resolution (E20/E21): over multiple seasons calibration is accuracy-neutral;
  RF's raw probabilities were already fine, XGB's genuinely needed it. Picks are
  now always taken from raw probabilities; RF displays raw; XGB keeps its
  calibrator. A tripwire catches degenerate calibrators.
- Lesson: a post-processing layer can quietly break a good model; monitor
  *distributions* (home-pick share), not just accuracy.
- Ties into the "split" badge and the win % shown under each margin.

**Figures:** reliability diagram (predicted vs actual home-win rate by bin), RF
raw vs isotonic (`e13_calibration.json`); home-pick share raw vs stale
calibrator, the ~97% (E19 audit / `e20_calibration.json` flips + consistency);
accuracy raw vs calibrated across the 16 backtest windows (`e21_backtest.json`).

### 6. More data didn't help
Learning curve (E15 Q1): with the test month fixed, training on ~1 season vs ~4
seasons (4.5× the games) made no difference for RF (76.5% both); half a season
already reached ~74.5%. Older seasons have different rosters and league trends,
so extra old data is roughly neutral. Practical answer: the models are
trustworthy after roughly 2–3 months of a new season. **Publish in Nov/Dec**
while readers are asking how reliable early-season picks are. Could pair with
#16 once that's resolved.

**Figures:** learning curve, accuracy (with seed ranges) vs number of training
games on a fixed test month (`e15_learning_curve.json`, 5 sizes x 5 seeds).
If paired with #16, add the split-badge decay curve.

### 7. Even the betting market can't call the playoffs
Follow-up to #4. On the same playoff games, the closing line itself only reached
AUC 0.648 / accuracy 64.7% / MAE 11.8 (E16), versus ~0.79 AUC for models in the
regular season. Our models trailed the market by 3–4pp AUC, but every
difference was within noise. Series-context features (game number, series score,
elimination games) didn't close the gap (E17), so playoff investment was capped.
Good to publish **in April** before the playoffs start.

**Figures:** models vs closing line on the same playoff games, acc/AUC/MAE
(`e16_playoff_ceiling.json`); model-minus-market differences with 95% CIs
(all crossing zero); series-context arm deltas with CIs (`e17_series_eval.json`).

### 8. Most of a player's scoring swing is luck
From P1/P2 + assessment §3.1: even given the *actual* minutes a player played,
points error only falls ~16% (4.94 → 4.18 MAE). About 85% of the miss is
single-game shooting and opportunity variance. Calibration is unbiased across
the range (stars aren't shaved, role players aren't inflated). The honest 90%
band for points is roughly ±10.5. Fantasy angle: why floors and ceilings matter
more than the point projection. Link to `/players/explore` line-clearing tool.

**Figures:** PTS error with predicted vs actual minutes (the 4.94 -> 4.18
decomposition); decile reliability, predicted vs actual PTS (from
`p2_player_validation.json`); distribution of PTS misses with the +-10.5 90%
band marked.

### 9. Beating a dumb-but-strong baseline
Marcel (Tom Tango's baseball projection: recent performance regressed to the
mean) adapted per-36 as the must-beat baseline; the ML model had to beat it with
paired significance or it wasn't earning its complexity. It did on 10 of 11
stats (e.g. minutes 4.93→4.63, points 5.23→5.03); steals were essentially at the
noise floor, where the simple model is just as good. Fantasy-points MAE 8.03 vs
8.41. Describe Marcel's idea; **don't publish our exact weights.**

**Figures:** per-stat % MAE improvement of XGB over Marcel with fold ranges,
STL near zero (`p1`/`p2_player_validation.json`); fantasy-points MAE Marcel vs
model. No weights on any axis.

### 10. Why steals and blocks are counted, not measured
Poisson for low-count stats: a "0.7 steals" point estimate says nothing about
how often a player gets 0, 1, or 2; a rate gives the whole distribution, which is
what the deep-dive's "model-implied" tile shows. Known limit: the model
over-forecasts 2+ blocks/steals for elite defenders (e.g. implied 66.6% vs
actual 63.2% in one bin), and a flexible correction made it *worse* (P5): an
overfitting lesson on sparse tails.

**Figures:** predicted vs actual frequency of 0 / 1 / 2+ steals and blocks by
predicted-rate bin, showing the elite-defender over-forecast (P1/P2 Poisson
calibration); with vs without the flexible tail correction
(`p5_tail_calibration.json`), worse with it.

### 11. Is the random forest really the worst model?
A single noisy month once suggested RF was much worse; across multi-season,
multi-seed tests it actually leads on winner accuracy and ranking (e.g. 3-season
× 16-window backtest: RF acc .657 / AUC .709 vs XGB .643 / .689), while XGB/NN
are ~0.2–0.3 points better on margins. RF's real trade-off: heavy regularization
makes its probabilities timid. Point: the three models have different strengths,
which is why the site shows all three. Re-check against current live numbers.

**Figures:** accuracy / AUC / MAE by model across the 16 backtest windows, as
ranges (`e21_backtest.json`); the single "bad month" highlighted inside that
spread; current live per-model numbers from the API.

### 13. Fewer features, better model (with care)
E22: removing more than half the inputs, chosen by out-of-sample permutation
importance at the group level, made the models significantly better at ranking
games on every model family and slightly better on margins; pruning further
went too far (margins got worse). Ties to #6: past a point, signal is the
constraint, not inputs. **Say "more than half"; never publish counts or which
groups survived** (the ranking reveals the production feature set).

**Figures:** dAUC and dMAE with 95% CIs for "pruned" and "pruned further" vs
all inputs, held-out month + pooled windows (`e22_w5.json`, `e22_windows.json`).
Label arms by description only; **never chart the importance ranking or
column counts.**

### 14. 99.9% training accuracy
E1: the original random forest scored 99.9% on games it trained on and 76% on new
games, a 24-point gap. Limiting how finely it could split the data cut the gap
to under 5 points; test accuracy dropped 1.3pp but ranking quality improved. A
clean, intuitive overfitting explainer. **No hyperparameter values.**

**Figures:** train vs test accuracy before and after limiting the forest (tuning
log E1: 99.9/76.2 -> 79.6/74.9). No stored output exists: re-run E0/E1 on the
frozen snapshot, ideally as a complexity sweep (train and test accuracy as the
model is allowed more splits) with an unlabeled "less -> more flexible" axis,
so no hyperparameter values appear.

### 15. The bug that made our neural net look broken
E6/E8: the neural net kept collapsing to 43% accuracy on one test window, and the
planned fix was an architecture change. Code review found duplicated and
constant-zero columns from a naming bug; fixing it took the NN from 43% to 74%
with no architecture change, and the "fix" was never needed. Lesson: check the
data before tuning the model. Keep the bug description generic (no column
naming scheme).

**Figures:** NN accuracy per walk-forward window before vs after the fix (the
43% -> 74% window stands out); check `e2_walk_forward_results.json` for the
pre-fix run, otherwise re-run on the backed-up buggy CSV
(`nba_ml_features.csv.backup_e8_buggy`).

### 18. How a static website grades itself every night
Architecture tour for a general audience: scheduled jobs pull results, grade
yesterday's picks, write today's; the site is static and fetches stored
predictions, plus the new build-time bake. Fine to describe at the
"S3 + CloudFront + scheduled containers" level; **no account IDs, bucket names,
IAM details, or endpoints beyond the public API.**

**Figures:** a data-flow diagram (scheduled jobs -> database -> API -> static site),
plus a timeline of one night's runs (JST). System article, so a diagram counts
as the figure. No resource names.

## Blocked / Hold / Ideas

### 12. Leakage (Hold)
E7: availability data originally came from post-game box scores, so the model
"knew" who played. Rebuilt from official pre-game injury reports; effect was
smaller than the literature's 2–5pp. E18: backfilled predictions on training
dates were optimistic, now refused by default. Strong topic, but explaining it
well means describing how availability enters the model. Publishable only as a
generic leakage explainer, or with Kai's sign-off.

**Figures (if reframed):** accuracy on backfilled training dates vs true
out-of-sample dates (E18), which shows the optimism without describing the
availability features.

### 16. Why the models sometimes disagree with themselves (Blocked)
Early 2026-27: each model's win-probability head and margin head pointed at
different teams in 20–57% of games (vs 0–3% last season), worst for XGB. The
site shows a "split" badge. Publish once the root cause is confirmed (suspected
sparse early-season rolling features); ideally with the decay curve as games
accumulate.

**Figures:** share of games where a model's win-probability pick and margin sign
disagree, per model, by week of the season (computable from the public
predictions API now); the decay curve is the article's centerpiece.

### 17. Player fatigue features (Hold)
P4: recent-workload features improved minutes predictions on every seed;
opponent hustle stats made turnover predictions worse (replicating the team-side
lesson from #1). The interesting part names adopted production features. Could
be reframed as "the feature that hurt" without naming the keepers.

**Figures (if reframed):** per-fold TOV dMAE with CIs for the opponent-hustle arm
(`p4_ab.json`), all on the wrong side of zero, without naming kept features.

### 19. Most of our traffic isn't human (Idea)
From `traffic_lab.md`: share of bot vs human traffic in CloudFront logs. Check
the numbers are current and that nothing exposes infrastructure detail.

**Figures:** daily requests split human / known bot / unknown (fresh Athena query
on CloudFront logs); top user-agent families. Needs a new query; no paths
that reveal infrastructure.

### 20. Monthly check-in (Recurring)
A short monthly post: how each model did last month, the market comparison,
notable hits and misses. Fresh content signals an active site to AdSense and
search. First one late November 2026, once a month of 2026-27 games is graded.

**Figures (standard set, reusable builder):** per-model accuracy and margin
MAE for the month vs the market (bars); cumulative accuracy through the month
(line); the month's biggest misses as a table.

### 21. Japanese versions of #1–#4 (Done 2026-10-27)
Each body file exports `<Name>En` and `<Name>Ja`; `BODIES` in
`app/articles/[slug]/page.tsx` maps slug → `{ en, ja }` and `ArticleShell`
picks by language (English body + notice when `ja` is missing). Kai's
glossary at the top of `web/lib/translations.ts` is the authority for
terminology (e.g. 市場の最終予想点差, 予測, スタッツ). Conventions used in the
article prose (not part of Kai's glossary): です・ます without ございます/おります,
and page names written as they appear in the nav. New articles should ship
with both versions.
