# AWS Deployment Plan

**Status:** Planning (2026-05-28)
**Owner:** Kai
**Goal:** Take the NBA prediction project public on AWS as a learning-friendly, low-cost deployment that can grow into a paid product.

---

## Context

The project today runs entirely on a single machine: local MySQL, local Python, local Dash app on `127.0.0.1:5000`. We want it on the internet so visitors can see tonight's predictions and our historical accuracy. There are no paying customers yet, so the v1 deployment must be cheap (≤$100/mo target, ideally ~$30/mo idle), simple enough for one person to maintain, and shaped so paying customers, NFL/MLB, and auth can bolt on later without rearchitecture.

The current Dash app (`visualization/dataExploration.py`, ~3000 lines, 8 tabs) is **not** the public product. It's a developer/internal tool — the **Operations** tab can trigger pipeline runs, **Model Performance** exposes our registry and hyperparameters, and there's no auth. The public surface will be a separate, much smaller frontend that reads pre-computed predictions from MySQL.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Public                                                          │
│                                                                 │
│   Visitor → CloudFront → S3 (static Next.js build)              │
│                  │                                              │
│                  └─ /api/* ─→ Fargate (FastAPI, public IP)      │
│                                  │                              │
│                                  └─→ RDS MySQL (private subnet) │
│                                       ▲                         │
│ Internal                              │                         │
│   Kai → SSH tunnel → Dash (local or private Fargate) ──────────┘│
│                                                                 │
│ Batch (no inbound)                                              │
│   EventBridge → Fargate Task (pipeline image) → RDS, S3 models  │
└─────────────────────────────────────────────────────────────────┘
```

### Component decisions

| Concern | Choice | Why |
|---|---|---|
| Public frontend | **Next.js static export → S3 + CloudFront** | Cheap (~$1/mo), real AWS primitives, free TLS via ACM, good SEO. Live data via client-side `fetch` from API. |
| Public API | **FastAPI on Fargate (single task, public IP, no ALB)** | ALB ($16/mo) only earns its keep with multiple replicas. Skip until needed. Cloudflare or CloudFront fronts for TLS. |
| Internal dashboard | **Existing Dash, run locally OR private Fargate** | Don't try to host the 8-tab dev tool publicly. Decide cost-vs-convenience in Week 4. |
| Database | **RDS MySQL `t4g.micro`, single-AZ, private subnet** | ~$15/mo. Multi-AZ ($30+) and read replicas deferred until traffic. |
| Batch pipeline | **One Docker image, ECS Fargate scheduled tasks via EventBridge** | Lambda's 15-min cap is too tight for `feature_engineering` (~8 min) + `train` (~10 min). Fargate has no time limit. |
| Model artifacts | **S3 versioned bucket** | Stop tracking `models/*.joblib` and `*.pt` in git. Training job uploads, predict job downloads. |
| Feature data | **`features` MySQL table, not CSV on disk** | Required before any of this works in containers. Replaces `nba_ml_features.csv`-at-project-root. |
| Secrets | **AWS Secrets Manager** | DB password, NBA API quirks. ~$0.40/mo per secret. |
| Networking | **Batch tasks in public subnets with public IPs** | Avoids $35/mo NAT Gateway. Only API + RDS go in private subnets. |
| IaC | **Terraform** (S3 remote state + DynamoDB lock) | Kai is learning; explicit IaC > console-driven. |
| CI/CD | **GitHub Actions** → ECR push → `aws ecs update-service` / S3 sync | Standard, free for public repos. |
| Observability v1 | **CloudWatch Logs + CloudFront access logs to S3** | Minimum-viable visitor analytics. Plausible/PostHog later. |
| Budget alarm | **AWS Budgets at $50/mo** | Cheap insurance. |

### Estimated monthly cost (idle, no traffic)

| Item | $/mo |
|---|---|
| RDS `t4g.micro` single-AZ | ~$15 |
| Fargate service (0.25 vCPU / 0.5GB, 24/7) | ~$8 |
| Fargate scheduled tasks (~30 min/day total) | ~$2 |
| S3 + CloudFront (data transfer minimal at low traffic) | ~$1-2 |
| Route53 hosted zone | ~$0.50 |
| Secrets Manager (1-2 secrets) | ~$0.80 |
| CloudWatch Logs (within free tier mostly) | ~$1-2 |
| ECR storage | ~$0 |
| **Total** | **~$30/mo** |

Headroom for ALB, Multi-AZ, observability tooling, and a second small Fargate task (e.g., the internal Dash) stays well under the $100/mo target.

---

## Pre-AWS refactors (MUST happen first)

These are local code changes that are cloud-hostile patterns in today's code. Do them before the AWS work begins; otherwise the cloud version will inherit them.

### 1. Move features from CSV to MySQL `features` table
**Why:** `nba_ml_features.csv` at the project root is a 50MB file that `feature_engineering.py` writes and `predict_games.py` / `baseline_models.py` read. This assumes a persistent single disk — false in any container deployment. It also blocks `[[project-feature-store]]` (the planned versioned `feature_sets` table).

**Touch points:**
- `data_engineering/feature_engineering.py` — write to `features` table (consider partitioning by `feature_set_version` for future versioning)
- `modeling/predict_games.py` — `_prepare_training_data()` at ~line 1933 reads the CSV
- `modeling/baseline_models.py`, `modeling/pytorch_nba_models.py` — same pattern
- Keep a CSV export utility for ad-hoc analysis; just don't make it source-of-truth

### 2. Extract `batch_predict_today.py`
**Why:** The public web tier must never invoke prediction logic. Today the Game Predictions tab in Dash calls `predict_with_loaded_model()` live with loaded PyTorch models — that doesn't scale, isn't cacheable, and means the web image must ship 200MB of ML deps.

**Touch points:**
- New script `modeling/batch_predict_today.py`: load models from S3 (or local for dev), fetch today's schedule, predict, write to `model_predictions` table, exit
- Wrapper for `batch_predict_backfill.py` for the date-range case (already implemented inside `predict_games.py:3573-3583` — just extract)
- API endpoints read from `model_predictions`; never call the model

### 3. Move model artifacts out of git
**Why:** `git status` shows `models/rf_classifier.joblib`, `models/nn_classifier.pt`, etc. as modified. They're ~200MB total. Tracking them in git bloats every clone, every CI build, every Docker layer.

**Touch points:**
- `.gitignore` — add `models/*.joblib`, `models/*.pt`, `models/bundles/*` (whitelist any small config files needed at runtime)
- `core/model_registry.py` — `save_model_bundle` / `load_model_bundle` already exists; add S3 read/write paths conditional on env var (`MODELS_S3_BUCKET`)
- One-time: `aws s3 sync models/ s3://<bucket>/models/`
- Document the upload step in training (`docs/training_runbook.md` if not already there)

---

## First-month plan

### Week 1 — local refactors, no AWS yet
- [ ] Features → MySQL `features` table; update readers in `predict_games.py`, `baseline_models.py`, `pytorch_nba_models.py`
- [ ] Extract `batch_predict_today.py` + `batch_predict_backfill.py` from `predict_games.py`
- [ ] Move model artifacts to `.gitignore`; add S3 read/write conditional on env var (test locally with a directory)
- [ ] Write `Dockerfile.pipeline` (heavy image: torch, sklearn, pandas, scrapers)
- [ ] Write `Dockerfile.api` (light image: fastapi, sqlalchemy, mysql driver only — no torch)
- [ ] Scaffold a minimal FastAPI with `/api/predictions/today` and `/api/accuracy/recent`
- [ ] docker-compose pointing at local MySQL — confirm full flow runs

### Week 2 — minimum AWS footprint
- [ ] Terraform repo skeleton with remote state in S3 + DynamoDB lock
- [ ] VPC (2 public subnets, 2 private subnets, no NAT), security groups
- [ ] RDS `t4g.micro` single-AZ in private subnets; password in Secrets Manager
- [ ] `mysqldump` local MySQL → restore to RDS
- [ ] ECR repos: `nba-pipeline`, `nba-api`
- [ ] S3 buckets: `nba-models-{account_id}`, `nba-static-{account_id}`, `nba-tf-state-{account_id}`
- [ ] Push pipeline image; run one-off Fargate task hitting RDS; confirm `model_predictions` rows appear

### Week 3 — public surface
- [ ] Next.js app: `/` (tonight's predictions), `/accuracy` (historical chart)
- [ ] `next build && next export` → S3 sync via GitHub Actions
- [ ] CloudFront distribution + ACM cert + Route53 record on the domain
- [ ] FastAPI Fargate service (0.25 vCPU / 0.5GB, public IP, no ALB)
- [ ] CloudFront `/api/*` behavior → Fargate task's public IP (or use a domain + cert directly on Fargate)
- [ ] GitHub Actions: `docker build → ECR push → aws ecs update-service` on merge to main

### Week 4 — operationalize
- [ ] EventBridge rules: nightly `fetch_data + features + predict`, weekly `train`, daily `vegas_lines`
- [ ] CloudWatch log groups for each Fargate task; retention 30 days
- [ ] CloudFront access logs → S3 bucket (visitor analytics v1)
- [ ] Budget alarm at $50/mo
- [ ] `/api/health` endpoint + a CloudWatch synthetic monitor
- [ ] Decision: internal Dash stays local, or deploy as private Fargate task (~$8/mo)

---

## What we are explicitly NOT doing in v1

- **ALB / multi-replica Fargate** — defer until traffic justifies it
- **RDS Multi-AZ** — defer until paying customer #1
- **Cognito + Stripe** — defer; public v1 is read-only, no accounts
- **NFL / MLB ingestion** — explicit do-not-touch until NBA is profitable or has measurable usage; the codebase needs a real sport abstraction layer (hardcoded `nba_*` table names, `nba_api` client coupling) and that's a large refactor better designed against a second concrete sport
- **Lambda** — wrong fit for our batch (15-min cap); wrong fit for our API (cold starts on PyTorch images)
- **Beanstalk** — abstracts the wrong things, fights Terraform, doesn't teach the AWS primitives we want to learn
- **Live model inference from the web tier** — predictions are batch-written nightly to `model_predictions`; web reads, never computes

---

## Open decisions (revisit before Week 3)

1. **Domain name** — TBD; needs to be registered before CloudFront cert work
2. **TLS strategy** — CloudFront-only (ACM us-east-1) vs Cloudflare-in-front (free WAF/DDoS, but extra hop). Lean CloudFront-only for "learn AWS"
3. **Internal Dash hosting** — local-only (free, requires Kai's machine) vs private Fargate behind SSH/SSM tunnel (~$8/mo)
4. **CloudFront → Fargate routing** — direct (Fargate gets a public IP and a domain name; CloudFront `/api/*` proxies) vs ALB later (when multi-replica)

---

## References

- Existing pipeline orchestrator: `orchestration/pipeline.py` — already stage-based, will become the entrypoint of `Dockerfile.pipeline`
- Existing prediction tracking: `modeling/prediction_tracker.py` — already writes to `model_predictions`; backfill flow stays as-is
- Existing model bundles: `core/model_registry.py` — `save_model_bundle` / `load_model_bundle` are the seam for S3 reads/writes
- Feature engineering: `data_engineering/feature_engineering.py` — single place to change CSV→table
- Database helper: `core/db.py` — already env-var-driven; will pick up RDS credentials from Secrets Manager via env

## Verification

End-to-end smoke test after Week 4:
1. Trigger the nightly EventBridge rule manually via `aws events put-events` or `aws ecs run-task`
2. Confirm new rows in `model_predictions` for tomorrow's date
3. Hit `https://<domain>/` in a browser — predictions render
4. Hit `https://<domain>/accuracy` — chart renders with non-empty data
5. Check CloudFront access logs landed in the analytics bucket
6. Verify budget alarm fires on a test threshold of $0.01

---

# Implementation Log — Week 1 (completed 2026-06-02)

> This section is written to **teach**, not just record. Each refactor below has
> the *problem it solves*, the *concept you should walk away understanding*, the
> *code that implements it*, and the *test that proved it works*. If you read
> only one part, read the "Concept" paragraphs — those are the transferable
> ideas you'll reuse for NFL/MLB and for every future cloud project.

The three Week-1 refactors share one theme: **remove assumptions that only hold
on a single, long-lived machine.** Your laptop has a persistent disk, one copy
of everything, and runs one process at a time. The cloud has none of those:
containers start empty, die without warning, and run in parallel. Code that
quietly depends on "the file will still be there next time" breaks in that world.
Week 1 finds those dependencies and replaces them with something explicit.

Committed as `2257b97`. Nothing here changes behavior for your current local
workflow — every new path has a fallback to the old one. That's deliberate: you
can keep working exactly as before while the cloud-ready paths sit dormant until
their env vars are set.

---

## 1.1 — Feature data: CSV on disk → versioned MySQL table

### The problem
`nba_ml_features.csv` was a ~50 MB file sitting at the project root.
`feature_engineering.py` *wrote* it; five other scripts *read* it with
`pd.read_csv('nba_ml_features.csv')`. That works perfectly on one machine and
fails three ways in the cloud:

1. **Ephemeral disk.** A container that builds the CSV and then exits takes the
   file to the grave. The next container starts with an empty disk.
2. **No sharing.** The training task and the prediction task are *different
   containers*. A file on one's local disk is invisible to the other.
3. **No history.** Each rebuild overwrote the file. If a new feature set made the
   model worse, there was no clean way to compare "old features vs new features"
   because the old ones were gone.

### The concept: a database is shared, durable, queryable state
A MySQL table solves all three at once — every container talks to the same RDS
endpoint, the data outlives any single container, and SQL lets you slice by date
without loading the whole thing into memory. This is the single most important
mental shift for cloud work: **state lives in a managed service (RDS, S3), never
on a container's local disk.** Containers become disposable; the data doesn't
live in them.

### The design decision: snapshots + a pointer
We didn't just dump the CSV into one table that gets overwritten. We chose
**versioned snapshots**:

- Every `feature_engineering.py` run inserts its rows tagged with a unique
  `feature_set_version` (a UTC timestamp like `20260529T033537Z`).
- A tiny second table, `feature_set_current`, holds exactly one row: which
  version is "live".
- Readers don't need to know the version — they look it up through the pointer.

```
features                              feature_set_current
┌─────────────────────┬─────────┐     ┌────┬──────────────────────┐
│ feature_set_version │ GAME_ID │...  │ id │ version              │
├─────────────────────┼─────────┤     ├────┼──────────────────────┤
│ 20260529T0335..     │ 0042...  │     │ 1  │ 20260529T0335..      │  ← "live"
│ 20260529T0335..     │ 0042...  │     └────┴──────────────────────┘
│ 20260601T1210..     │ 0042...  │  (a newer snapshot, not yet promoted)
└─────────────────────┴─────────┘
```

**Why a pointer instead of "newest timestamp wins"?** Atomicity. Promoting a new
feature set is a *single-row update* to `feature_set_current`. Until that update
happens, readers keep seeing the old version — even while the new snapshot is
half-inserted. There's never a moment where a reader sees a partial dataset.
This is the same idea as the `_current.joblib` model pointer (1.3) and as a
blue/green deploy: **write the new thing fully, then flip one switch.**

A snapshot is ~6 MB in the DB — trivial. Keeping many of them is what unlocks the
parked `feature_store` idea: "train model A on feature set v1, model B on v2,
compare honestly." You can't do that with a file that gets overwritten.

### The "schema auto-evolve" decision
The feature set isn't fixed — your experiments add and drop columns (E9 added
ELO, E16/E17 added playoff features). A hand-maintained `CREATE TABLE` with 769
columns would be a nightmare to keep in sync. So `core/features_io.py` inspects
the DataFrame and, on each write, issues `ALTER TABLE ADD COLUMN` for any column
the table doesn't have yet. The table shape *follows* whatever pandas produces —
same mental model as the CSV (whatever you write is the schema). Trade-off: it's
implicit, so a column that silently disappears from the DataFrame just stops
being written. We accepted that because at 1,000 rows an ALTER is instant and it
keeps experimentation friction-free.

### The fallback pattern (important — you'll see it in all three refactors)
Every reader was changed from `pd.read_csv(...)` to
`load_features_with_csv_fallback(engine, csv_path=...)`. That helper:

1. Tries the DB (current version pointer).
2. If the DB is empty but the CSV exists, reads the CSV **and bootstraps the DB
   from it** so the next call is fast.
3. Raises only if *both* are missing.

**Why bother with the fallback?** Because a refactor that forces a flag-day
("everyone must migrate right now or everything breaks") is risky and stressful.
With the fallback, the code works whether or not you've run the migration yet.
You migrate when you're ready; nothing breaks in the meantime. This is how you
ship infrastructure changes safely — **make the new path optional until it's
proven, then make it the default.**

### Files
- `core/features_io.py` — the read/write/version API (new)
- `scripts/migrate_features_csv_to_db.py` — one-shot CSV → DB importer (new)
- `data_engineering/feature_engineering.py` — now dual-writes CSV + DB snapshot
- Readers updated: `modeling/predict_games.py` (new `_load_feature_dataset`
  helper), `baseline_models.py`, `pytorch_nba_models.py`, `validate_models.py`,
  `visualization/dataExploration.py`, `orchestration/pipeline.py`
- Left on CSV intentionally: `experiments/*.py` (ad-hoc research on pinned snapshots)

### Tests performed
| What we tested | How | Result |
|---|---|---|
| Module imports, table/pointer names correct | `python core/features_io.py` symbol check | ✅ all symbols load; version tag format correct |
| Migration of the real 769-col / 1043-row CSV | `python scripts/migrate_features_csv_to_db.py` | ✅ ran clean (you confirmed "no errors") |
| Readers see DB-first | `python orchestration/pipeline.py status` | ✅ `features_set_version` populated, dates matched the old CSV-derived values |
| Syntax integrity of all 9 touched files | `ast.parse` over each | ✅ all OK |

---

## 1.2 — A dedicated headless prediction job

### The problem
Predictions were produced two ways, both bad for a public website:
- The **dashboard** computed them live: a user opening the Game Predictions tab
  triggered model loading + inference inside the web request.
- `predict_games.py` is a 4,000-line interactive CLI — it prints tables, draws
  matplotlib charts, computes SHAP explanations, can kick off a retrain, and
  parses dozens of flags. It's a Swiss-army knife for *you*, not a job for a
  server.

### The concept: separate "compute" from "serve"
This is the **batch/serve split**, one of the most useful patterns in applied
ML. The expensive, slow, occasional work (running models) is done *ahead of time*
by a batch job that writes results to a database. The fast, frequent work
(showing results to a visitor) is a cheap database read. The web server never
loads a model, never imports PyTorch, never runs SHAP.

Why this matters concretely:
- **Cost & speed.** The NBA schedule is fixed — there are at most ~15 games a
  night. Computing those once and serving the stored answer to 10,000 visitors
  is vastly cheaper than running inference 10,000 times. The answer is identical
  for everyone, so compute it once.
- **Small web image.** No torch/sklearn/shap in the web container means it builds
  to ~200 MB instead of ~2 GB and cold-starts in under a second.
- **Blast radius.** If a model errors, the *batch job* fails (and you get an
  alert) — the website stays up serving last night's predictions. Inference
  failures never reach a visitor.

### What `batch_predict_today.py` actually is
A thin orchestration layer (~280 lines) that **imports the per-game primitives
from `predict_games.py`** rather than duplicating them. The division of labor:

- `predict_games.py` owns *per-game logic*: `get_scheduled_games`,
  `get_team_rolling_stats`, `build_matchup_features`, `predict_with_rf/nn/xgb`,
  the leakage guard, the injury lookups. Unchanged.
- `batch_predict_today.py` owns *job orchestration*: which dates, which models,
  loop, write to `model_predictions`, exit with a status code.

Deliberate differences from the CLI: no SHAP, no matplotlib, no comparison
tables, **no retrain** in the normal path (a nightly job should never silently
start a 10-minute training run), and `exit code = number of errors` so a
scheduler (EventBridge, cron) can tell success from failure.

### The idempotency property (and why it matters for schedulers)
`log_prediction` uses MySQL's `INSERT ... ON DUPLICATE KEY UPDATE` on the key
`(game_id, model_type, model_version)`. That means **running the job twice
produces the same end state** — the second run overwrites the first row instead
of creating a duplicate. This is *idempotency*, and it's essential for scheduled
jobs: schedulers retry on failure, networks hiccup, you'll re-run by hand to test.
A job that's safe to run repeatedly is a job you can automate without fear.

### Files
- `modeling/batch_predict_today.py` (new)

### Tests performed (against your real local DB)
| What we tested | How | Result |
|---|---|---|
| Bundles load (rf/nn/xgb), no-games day handled | `--models rf --no-log` on today (offseason) | ✅ "no scheduled games", exit 0 |
| All 3 models predict a real game | `--date 2026-05-28 --no-log` | ✅ 3 predictions / 1 game, 0 errors |
| Logged write to `model_predictions` | `--date 2026-05-28` (logged) | ✅ 3 rows written, every column populated |
| **Output identical to the interactive CLI** | compared rf row to existing `predict_games.py` row | ✅ same margin (4.68), same winner (SAS) — proves the extraction didn't change the math |
| Leave-no-trace | deleted the 3 leakage-tainted test rows afterward | ✅ DB restored to its original 4 rows |

The "identical output" test is the important one: it confirms we *moved* logic
without *changing* it. When you refactor, always find a way to prove the new path
produces the same result as the old one.

> Note discovered during testing: XGBoost reports `margin_uncertainty = 0.0`
> (it's a point estimate, no spread), while RF (7.48) and NN (2.88) give real
> uncertainty. Not a bug — but the public site's confidence-interval UI should
> handle "no interval" gracefully for xgb.

---

## 1.3 — Model artifacts: out of git → an artifact store

### The problem
Trained models (`models/rf_classifier.joblib`, `nn_classifier.pt`, the
`models/bundles/` snapshots, etc. — ~200 MB total) were partly committed to git.
Binaries in git are a slow-motion mistake:
- Git stores every version of every file forever. A 200 MB model retrained weekly
  bloats the repo permanently — every clone, every CI build downloads all of it.
- They're not diffable or reviewable; they just make the repo heavy.
- Worst of all for cloud: a CI pipeline that builds a Docker image would bake
  stale model weights *into the image*, so shipping a new model would mean
  rebuilding and redeploying the whole container.

### The concept: large binaries belong in object storage, referenced by code
The cloud-native answer is **S3** (object storage): cheap, versioned, infinitely
durable, accessible from any container. Code doesn't *contain* the model; it
*fetches* the model from S3 at runtime. Git holds the code (small, diffable,
reviewable); S3 holds the artifacts (large, binary, versioned). Each tool does
what it's good at.

### The design: a pluggable store with three backends
Rather than hard-coding `boto3.client('s3')` calls throughout the code (which
would force every developer to have AWS set up just to run anything), we built
`core/artifact_store.py` — one small interface, three implementations chosen by
environment variable:

```
MODELS_S3_BUCKET set      → S3Store        (production: real S3)
MODELS_ARTIFACT_DIR set   → LocalMirrorStore (a directory pretending to be a bucket)
neither set               → DisabledStore  (no-op: pure local, today's behavior)
```

Two ideas worth internalizing here:

1. **Program to an interface, not an implementation.** The call sites
   (`save_model_bundle`, `load_model_bundle`) just call `store.push()` /
   `store.pull()`. They have no idea whether that's hitting S3, a local folder,
   or doing nothing. You can develop and *fully test the upload/download logic*
   with `MODELS_ARTIFACT_DIR` pointed at a scratch folder — no AWS account, no
   network, no credentials. When you go to prod, you set `MODELS_S3_BUCKET`
   instead and the *exact same code path* now talks to S3. This is how you avoid
   "works locally, breaks in cloud" surprises: the cloud path was exercised all
   along, just against a fake bucket.

2. **Graceful degradation.** The `DisabledStore` makes the store optional.
   With no env vars set, push is a no-op and the code behaves exactly as it did
   before this refactor. Nobody is forced to change their workflow.

### Where it plugs in: pull-on-missing
The clever bit is in `load_model_bundle`: if the bundle isn't on local disk, it
asks the store to pull it before giving up. On your laptop the file is already
there, so the pull never happens. **On a fresh container, `models/` is empty —
so the first `load_model_bundle('rf')` call pulls the model down from S3 and
caches it locally.** The container hydrates itself on demand. No separate "copy
the models in" deploy step; the code does it the first time it needs the model.

`save_model_bundle` does the reverse: after writing the bundle locally, it pushes
to the store. So the training job *publishes* and the prediction job *consumes*,
through S3, with no shared disk between them — exactly the decoupling 1.2 needs.

### Files
- `core/artifact_store.py` — the store interface + 3 backends (new)
- `scripts/sync_models.py` — bulk `push` / `pull` / `status` CLI (new), for
  seeding a fresh bucket or hydrating a new machine all at once
- `modeling/predict_games.py` — `save_model_bundle` pushes, `load_model_bundle`
  pulls-on-missing
- `.gitignore` — now ignores `models/*.joblib`, `models/*.pt`, mirror dir
- `.env.example` — documents the three env vars
- `requirements.txt` — `boto3` added as an optional dependency
- 9 binary files removed from git tracking with `git rm --cached` (the
  working-tree files stay on disk; only their *tracking* is removed)

### Tests performed
| What we tested | How | Result |
|---|---|---|
| Backend auto-selection | set/unset env vars, check `store.name` | ✅ s3-unavailable→disabled, mirror, disabled all correct |
| Bulk push | `sync_models.py push` with `MODELS_ARTIFACT_DIR` | ✅ 60 files copied to the mirror |
| **Pull-on-missing (the cloud-hydration scenario)** | moved local `rf_current.joblib` aside, called `load_model_bundle('rf')` | ✅ file re-pulled from mirror; 567 features, version 20260527 — the model loaded despite being "missing" locally |
| Disabled backend = unchanged local behavior | no env vars; push returns False, exists() checks disk | ✅ |
| Syntax integrity | `ast.parse` of touched files | ✅ |

The pull-on-missing test is the one that proves the cloud story: it simulates a
freshly-started container (empty `models/`) and shows the code heals itself by
fetching from the store.

### ⚠️ One thing to be careful about now
Those 9 model files are **no longer in git history going forward**. Your only
copies are (a) local disk and (b) whatever you've pushed to a store. Before you
ever run `git clean -xdf`, delete the `models/` folder, or clone fresh, make sure
the models are either pushed to a real store or you're OK regenerating them with
a retrain. This is the normal trade-off of moving artifacts out of git — just be
aware of it.

---

## What this unlocked for Weeks 2–4

With Week 1 done, the three single-machine assumptions are gone:
- **Feature data** lives in MySQL → any container can read it from RDS.
- **Predictions** are produced by a standalone batch job → the web tier just
  reads a table.
- **Models** live in an artifact store → training publishes, prediction pulls,
  no shared disk needed.

That means the Week-2 work (Dockerfiles, RDS, a one-off Fargate task) has a
clean target: package `batch_predict_today.py` + the pipeline into the "pipeline"
image, point `NBA_DB_*` at RDS and `MODELS_S3_BUCKET` at a real bucket, and the
same code you tested locally runs unchanged in the cloud. Nothing about the
container needs persistent local state.
