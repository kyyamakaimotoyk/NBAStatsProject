# Docs index — start here

*Maintained map of `docs/`, written so a reader (human or LLM) can find the one
section it needs without loading the large files. Updated 2026-10-30.*

**Read order for a new session:** this file → [`CHANGELOG.md`](CHANGELOG.md) (what
changed recently, with links) → only the doc sections the task needs. The two big
files are `model_tuning_log.md` (~2,060 lines) and `aws_deployment_plan.md`
(~1,380): grep them, don't read them whole.

## Where the truth lives

| Question | Canonical source |
|---|---|
| Why is the model built this way? Was X tried? | [`model_tuning_log.md`](model_tuning_log.md): master table at the top (one row per experiment, E1-E26 team, P1-P7 player), then one `## <date> — Experiment N` section each. `grep -n "^## 20" docs/model_tuning_log.md` lists them. |
| What changed recently, and where is it written up? | [`CHANGELOG.md`](CHANGELOG.md) |
| Big-picture model critique and roadmap | [`model_assessment_2026-07.md`](model_assessment_2026-07.md) (+ 2026-10-30 Addendum) |
| Which features the production models use | `core/features.py` (toggles + E22 keep-list), not any doc |
| What is deployed and how | README Part I + [`aws_deployment_plan.md`](aws_deployment_plan.md); `infra/*.tf` is authoritative |
| Calendar-bound / pending ops work for Kai | [`preseason_checklist.md`](preseason_checklist.md) |
| Article backlog, disclosure rules, product ideas (P-1, P-2) | [`articles.md`](articles.md) |
| Table schemas | [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md); `modeling/prediction_tracker.py` for `model_predictions` |
| Is the public track record like-for-like? | `python scripts/check_track_record.py`; tuning log §E26 |

## Every doc

Status: **live** = kept current; **frozen** = point-in-time, superseded parts noted
inside; **lab** = learning notes, not project state.

| Doc | Lines | Status | What it is |
|---|---|---|---|
| [`model_tuning_log.md`](model_tuning_log.md) | 2060 | live, append-only | Canonical experiment log, E1-E26 + P1-P7. Past entries frozen; corrections are dated inline notes. |
| [`CHANGELOG.md`](CHANGELOG.md) | — | live | Dated change history linking to everything below |
| [`model_assessment_2026-07.md`](model_assessment_2026-07.md) | 450 | frozen + addendum | July 2026 review: RF-worse premise false, feature saturation, Vegas gap, impact metrics. §2.3 margin claim corrected 2026-10-30. |
| [`articles.md`](articles.md) | 620 | live | /articles backlog + publication log, disclosure line, figures rule, product ideas P-1/P-2 |
| [`preseason_checklist.md`](preseason_checklist.md) | 80 | live | Ops checklist incl. the P-2/E26 run order |
| [`player_projections_plan.md`](player_projections_plan.md) | 380 | live (phases A-D built) | Player model → /players → advisor plan and build notes |
| [`ad_monetization_plan.md`](ad_monetization_plan.md) | 200 | live | AdSense plan, rejection, re-review log |
| [`advisor_scope_plan.md`](advisor_scope_plan.md) | 110 | frozen (implemented) | Widening the LLM advisor beyond tonight |
| [`aws_deployment_plan.md`](aws_deployment_plan.md) | 1380 | frozen (deployed) | The plan that took the site public; header status is stale |
| [`playoff_improvement_plan.md`](playoff_improvement_plan.md) | 170 | frozen | Playoff modeling plan after E15-E17 (investment capped) |
| [`post_e11_synthesis.md`](post_e11_synthesis.md) | 140 | frozen (2026-05-19) | Where things stood after E11; the "MAE ~5 wall" framing |
| [`e3_ablation_report.md`](e3_ablation_report.md) | 240 | frozen | E3/E12 noise-aware ablation report |
| [`e13_calibration_report.md`](e13_calibration_report.md) | 140 | frozen | E13 isotonic calibration (later demoted for RF by E21) |
| [`e14_intervals_report.md`](e14_intervals_report.md) | 120 | frozen | E14 conformal margin intervals |
| [`e15_cross_context_report.md`](e15_cross_context_report.md) | 120 | frozen | E15 regular season vs playoffs, learning curve |
| [`p1_player_validation_report.md`](p1_player_validation_report.md) | 320 | frozen (superseded by P2) | P1 player-model validation |
| [`p2_player_validation_report.md`](p2_player_validation_report.md) | 350 | frozen (current baseline) | P2 player validation, incl. playoffs |
| [`p3_impact_metrics_report.md`](p3_impact_metrics_report.md) | 20 | frozen | P3 eRAPTOR player features (rejected) |
| [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) | 430 | reference | MySQL schema |
| `terraform_lab`, `docker_lab`, `cicd_lab`, `ops_lab`, `traffic_lab`, `frontend_lab`, `troubleshooting_lab` | 200-270 each | lab | Hands-on notes per tool; `troubleshooting_lab` = the 2026-06-29 outage |
| `bedrock_lab`, `bedrock_ops_lab` (+ `lab9_verify.py`) | 1250 / 780 | lab | AIP-C01 Bedrock labs; ops labs 9-15 env-gated in code |

## Code entry points (for orientation, not documentation)

| Job | File |
|---|---|
| Nightly cloud batch | `modeling/batch_predict_today.py` |
| Weekly retrain stage | `orchestration/pipeline.py` `TrainStage` → `modeling/retrain_models.py` |
| Training loaders (RF/XGB/NN) | `modeling/predict_games.py` `load_or_train_*` |
| Bundle sync check | `modeling/bundle_sync.py` |
| Walk-forward track record | `modeling/walkforward_backfill.py` |
| Public API | `api/main.py`, `api/queries.py` |
| Article figures | `scripts/build_article_figures.py` → `web/data/articles/` |
| Experiments | `experiments/` (harness: `harness.py`, `loop_ab.py`, `loop_player_ab.py`); results in `outputs/` |

## House rules that affect any change

- Tuning log is append-only: correct with a dated inline note, never rewrite.
- A feature or model change needs multi-seed + paired tests (E12) before it is kept.
- Public content never discloses feature lists/counts, hyperparameters, or pipeline
  internals (articles.md "Disclosure line").
- Writes to local MySQL / RDS, terraform applies and image pushes are run by Kai;
  write the exact commands into `preseason_checklist.md` or the relevant doc.
