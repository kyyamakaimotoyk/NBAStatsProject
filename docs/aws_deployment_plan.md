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
