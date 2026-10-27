# Articles: ideas and publication log

*Started 2026-10-27. Tracks every article idea for the `/articles` section of
hoopmodel.com: what it would say, which report it draws on, and whether it's
published. Ideas came from a pass over every report in `docs/`.*

Why this section exists: AdSense rejected the site for low-value content
(see `docs/ad_monetization_plan.md`). Original written analysis is the strongest
fix, and the experiment reports are full of findings that are interesting to a
general basketball audience.

## How to publish one

1. Write the body as a component in `web/components/articles/<Name>.tsx`
   (plain JSX prose; `Link` for internal links).
2. Add the metadata entry (slug, date, read time, EN/JA title + summary,
   `hasJapanese`) to the top of `ARTICLES` in `web/lib/articles.ts`.
3. Register the body in `BODIES` in `web/app/articles/[slug]/page.tsx`.
   The index page, per-article metadata and sitemap pick it up automatically.
4. Recompute any live numbers from the API right before publishing
   (`/api/performance/results?days=1100` etc.). Never copy stale figures from
   an old report when a current one exists.
5. Update the status in the table below.

## Disclosure line (applies to every article)

OK to publish: questions, methods (paired tests, walk-forward validation,
conformal intervals), verdicts, effect sizes, public baselines (Elo, Marcel,
the betting market), public data sources.

Not OK: exact feature lists or feature counts, hyperparameter values, how the
injury/availability features are built, data-pipeline internals, code, and
anything that would let someone rebuild the production feature set. When a
finding is only interesting *because* of a specific production feature, mark it
**Hold** instead of publishing a vague version.

## Status key

- **Published**: live on the site (date = publication date)
- **Ready**: findings are final and safe to publish; just needs writing
- **Blocked**: the underlying question is still open
- **Hold**: disclosure concern; publish only if reframed or approved by Kai

## Summary table

| # | Working title | Source(s) | Status |
|---|---|---|---|
| 1 | Signal or noise? How we decide whether a model change is real | tuning log E12, E24, P7/P7b; `e3_ablation_report.md` | **Published** 2026-10-27 (EN) |
| 2 | Why nobody predicts NBA margins within five points | `post_e11_synthesis.md` + live API numbers | **Published** 2026-10-27 (EN) |
| 3 | Last season's impact ratings don't help predict this season | `p3_impact_metrics_report.md`, tuning log E25, assessment §5 | **Published** 2026-10-27 (EN) |
| 4 | Playoff games are harder to predict, and it's not the model's fault | `e15_cross_context_report.md` (Q2) | **Published** 2026-10-27 (EN) |
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
| 21 | Japanese versions of #1–#4 | — | Ready (task, not an idea) |

## Published

### 1. Signal or noise?
`/articles/signal-or-noise/`. A 230-game test month makes accuracy wobble ±5pp
from seeds and game draw alone; paired tests (McNemar, paired t, bootstrap of the
AUC difference) are what separate signal from that. Elo kept; lineup stats
(the "+2.6pp" result) and opponent-adjusted stats dropped. Team tuning search
didn't transfer to held-out data (7–7 on disagreements); player tuning did (9/11
stats), with blocks kept on original settings. Ends with the working rules.

### 2. Why nobody predicts NBA margins within five points
`/articles/margin-floor/`. Live numbers (2026-10-27, 4,203 games): margin SD
≈16, median game decided by 10, constant "home by 2" guess misses by 12.7,
models ≈11.5, closing line 10.8, only 31% of games within 5 of the line; model
error p50 9.5 / p80 18.7. Explains shooting variance, game state, late info.
**Refresh these numbers each season.**

### 3. Last season's impact ratings don't help predict this season
`/articles/impact-ratings/`. Player model: 0/11 stats pass, biggest ΔMAE −0.007,
features used but redundant. Team model: standalone r = 0.28 and 65% home-win
when positive, but null in-model, null pooled over 21 windows, slightly worse
Oct–Dec. Open item: daily-updated ratings untested. **Judgment call flagged to
Kai:** the article describes the rejected experiment's roster construction
(recent appearances minus Out/Doubtful); cut if too close to the line.

### 4. Playoff games are harder to predict
`/articles/playoff-predictability/`. Five seasons, ~630 control / ~400 playoff
games. Accuracy 71→64% (RF), 69→62% (XGB); AUC ~0.79→0.60–0.64; 90% margin
ranges still cover 88–90%, MAE 11.9→12.1. Causes: compressed strength gap,
slower pace, series adjustments. Play-in n=30, no claim.

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

### 6. More data didn't help
Learning curve (E15 Q1): with the test month fixed, training on ~1 season vs ~4
seasons (4.5× the games) made no difference for RF (76.5% both); half a season
already reached ~74.5%. Older seasons have different rosters and league trends,
so extra old data is roughly neutral. Practical answer: the models are
trustworthy after roughly 2–3 months of a new season. **Publish in Nov/Dec**
while readers are asking how reliable early-season picks are. Could pair with
#16 once that's resolved.

### 7. Even the betting market can't call the playoffs
Follow-up to #4. On the same playoff games, the closing line itself only reached
AUC 0.648 / accuracy 64.7% / MAE 11.8 (E16), versus ~0.79 AUC for models in the
regular season. Our models trailed the market by 3–4pp AUC, but every
difference was within noise. Series-context features (game number, series score,
elimination games) didn't close the gap (E17), so playoff investment was capped.
Good to publish **in April** before the playoffs start.

### 8. Most of a player's scoring swing is luck
From P1/P2 + assessment §3.1: even given the *actual* minutes a player played,
points error only falls ~16% (4.94 → 4.18 MAE). About 85% of the miss is
single-game shooting and opportunity variance. Calibration is unbiased across
the range (stars aren't shaved, role players aren't inflated). The honest 90%
band for points is roughly ±10.5. Fantasy angle: why floors and ceilings matter
more than the point projection. Link to `/players/explore` line-clearing tool.

### 9. Beating a dumb-but-strong baseline
Marcel (Tom Tango's baseball projection: recent performance regressed to the
mean) adapted per-36 as the must-beat baseline; the ML model had to beat it with
paired significance or it wasn't earning its complexity. It did on 10 of 11
stats (e.g. minutes 4.93→4.63, points 5.23→5.03); steals were essentially at the
noise floor, where the simple model is just as good. Fantasy-points MAE 8.03 vs
8.41. Describe Marcel's idea; **don't publish our exact weights.**

### 10. Why steals and blocks are counted, not measured
Poisson for low-count stats: a "0.7 steals" point estimate says nothing about
how often a player gets 0, 1, or 2; a rate gives the whole distribution, which is
what the deep-dive's "model-implied" tile shows. Known limit: the model
over-forecasts 2+ blocks/steals for elite defenders (e.g. implied 66.6% vs
actual 63.2% in one bin), and a flexible correction made it *worse* (P5): an
overfitting lesson on sparse tails.

### 11. Is the random forest really the worst model?
A single noisy month once suggested RF was much worse; across multi-season,
multi-seed tests it actually leads on winner accuracy and ranking (e.g. 3-season
× 16-window backtest: RF acc .657 / AUC .709 vs XGB .643 / .689), while XGB/NN
are ~0.2–0.3 points better on margins. RF's real trade-off: heavy regularization
makes its probabilities timid. Point: the three models have different strengths,
which is why the site shows all three. Re-check against current live numbers.

### 13. Fewer features, better model (with care)
E22: removing more than half the inputs, chosen by out-of-sample permutation
importance at the group level, made the models significantly better at ranking
games on every model family and slightly better on margins; pruning further
went too far (margins got worse). Ties to #6: past a point, signal is the
constraint, not inputs. **Say "more than half"; never publish counts or which
groups survived** (the ranking reveals the production feature set).

### 14. 99.9% training accuracy
E1: the original random forest scored 99.9% on games it trained on and 76% on new
games, a 24-point gap. Limiting how finely it could split the data cut the gap
to under 5 points; test accuracy dropped 1.3pp but ranking quality improved. A
clean, intuitive overfitting explainer. **No hyperparameter values.**

### 15. The bug that made our neural net look broken
E6/E8: the neural net kept collapsing to 43% accuracy on one test window, and the
planned fix was an architecture change. Code review found duplicated and
constant-zero columns from a naming bug; fixing it took the NN from 43% to 74%
with no architecture change, and the "fix" was never needed. Lesson: check the
data before tuning the model. Keep the bug description generic (no column
naming scheme).

### 18. How a static website grades itself every night
Architecture tour for a general audience: scheduled jobs pull results, grade
yesterday's picks, write today's; the site is static and fetches stored
predictions, plus the new build-time bake. Fine to describe at the
"S3 + CloudFront + scheduled containers" level; **no account IDs, bucket names,
IAM details, or endpoints beyond the public API.**

## Blocked / Hold / Ideas

### 12. Leakage (Hold)
E7: availability data originally came from post-game box scores, so the model
"knew" who played. Rebuilt from official pre-game injury reports; effect was
smaller than the literature's 2–5pp. E18: backfilled predictions on training
dates were optimistic, now refused by default. Strong topic, but explaining it
well means describing how availability enters the model. Publishable only as a
generic leakage explainer, or with Kai's sign-off.

### 16. Why the models sometimes disagree with themselves (Blocked)
Early 2026-27: each model's win-probability head and margin head pointed at
different teams in 20–57% of games (vs 0–3% last season), worst for XGB. The
site shows a "split" badge. Publish once the root cause is confirmed (suspected
sparse early-season rolling features); ideally with the decay curve as games
accumulate.

### 17. Player fatigue features (Hold)
P4: recent-workload features improved minutes predictions on every seed;
opponent hustle stats made turnover predictions worse (replicating the team-side
lesson from #1). The interesting part names adopted production features. Could
be reframed as "the feature that hurt" without naming the keepers.

### 19. Most of our traffic isn't human (Idea)
From `traffic_lab.md`: share of bot vs human traffic in CloudFront logs. Check
the numbers are current and that nothing exposes infrastructure detail.

### 20. Monthly check-in (Recurring)
A short monthly post: how each model did last month, the market comparison,
notable hits and misses. Fresh content signals an active site to AdSense and
search. First one late November 2026, once a month of 2026-27 games is graded.

### 21. Japanese versions of #1–#4 (Task)
Transcreate per the glossary in `web/lib/translations.ts`; Kai edits
terminology. Flip `hasJapanese` and branch the body on `useLang()` (or add a
JA body component) once written.
