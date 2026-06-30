# Docker Hands-On Lab — poke inside your own images

A self-contained, re-readable lab for building real Docker intuition using **this
project's** images (`nba-pipeline:local`, `nba-api:local`). Companion to the
"Kai Learning" Parts A–E in `docs/aws_deployment_plan.md`; this file is the
*do-it-with-your-hands* half.

> Shell: **cmd.exe**. Your terminal already has `docker` on PATH. Any working
> directory is fine for `docker run` (the image is self-contained); the
> build-context investigations at the end need the **project root**.

## The lab series

Five hands-on companions to the "Kai Learning" parts in `aws_deployment_plan.md`,
each grounded in this repo's real code. Read in any order:

| Lab | Covers | Pairs with |
|---|---|---|
| **Docker** (this lab) | images, layers, containers, the troubleshooting loop | Parts A, D, E |
| [Terraform](terraform_lab.md) | state, plan/apply, drift, the dependency graph | Parts C, F–I |
| [Frontend / TypeScript](frontend_lab.md) | Next.js, types-as-contract, client fetch, static export | Part H |
| [CI/CD](cicd_lab.md) | GitHub Actions, OIDC, path filters, push-to-deploy | Part I |
| [Ops](ops_lab.md) | scheduling, alarms, budgets, logs, the egress probe | Part J |

---

## 0. Prerequisites

1. **Docker Desktop running.** Check:
   ```cmd
   docker info
   ```
   If you get `open //./pipe/dockerDesktopLinuxEngine: ... cannot find the file`,
   the engine is down — launch Docker Desktop and wait until `docker info`
   succeeds.
2. **The image exists.** Check:
   ```cmd
   docker images | findstr nba
   ```
   You want `nba-pipeline:local`. If it's gone, rebuild: `docker compose build`.

---

## The mental model (30-second recap)

- **Image** = a frozen, complete environment + your code. **Container** = one
  running instance of it (immutable — you replace it, you don't edit it).
- A Dockerfile is a stack of **layers**, one per filesystem-changing instruction.
- Every line exists because a **constraint of the job** forced it. Reading a
  Dockerfile well = going *constraint → line*.

---

## Exercise 1 — `docker history`: see the layers and their sizes

```cmd
docker history nba-pipeline:local
```
For a cleaner view (size + instruction only):
```cmd
docker history nba-pipeline:local --format "{{.Size}}\t{{.CreatedBy}}" --no-trunc
```

**Layers print newest-first.** Captured output for this image, mapped to the
`Dockerfile.pipeline` instructions:

| Size | Instruction | Meaning |
|---|---|---|
| 0 B | `CMD`, `USER`, `ENV` | metadata — free, no filesystem change |
| ~90 kB | `useradd && mkdir && chown` | the permission fix; tiny, near the top |
| **3.19 GB** | `COPY . .` | your project code+context ⚠️ *suspiciously large* (see Ex. 5) |
| 1.78 GB | `pip install -r requirements-pipeline.txt` | the ML stack |
| 879 MB | `pip install torch (CPU)` | the single heaviest dep |
| 341 MB | `apt-get install build-essential …` | compilers to build `mysqlclient` |
| ~130 MB | `python:3.12-slim` base layers (bottom) | the foundation |

**What to notice:**
- The big costs are **deps** (torch + pip ≈ 2.6 GB), exactly why they get their
  own layers placed **before** your code — so editing code doesn't re-run them.
- The `chown` fix is ~90 kB and sits near the top: a code/runtime change rebuilds
  only the cheap top layers, never the 2.6 GB below. **That's layer caching, and
  it's the whole reason a one-line fix rebuilds in seconds.**

---

## Exercise 2 — who does the container run as?

```cmd
docker run --rm nba-pipeline:local whoami
```
Expect: **`appuser`**.

- `docker run` starts a throwaway container; `--rm` deletes it on exit; the word
  after the image name (`whoami`) is the command run *inside*.
- Proves the `USER appuser` line works — the container is **not** root. Running as
  a non-root user is container hygiene (and required by some platforms).

---

## Exercise 3 — see the permission fix made visible

```cmd
docker run --rm nba-pipeline:local ls -la /app
```
Look at the **owner** column:
- `models`, `logs`, `outputs` → owned by **appuser** (uid 10001)
- everything else (your code, copied in as root) → owned by **root**

That split *is* the bug fix from Week 2.5. Because the container runs as
`appuser`, it can only write where it owns — and the predictor writes model
bundles into `models/bundles/` (pulled from S3) and logs/outputs. Without the
`chown`, those writes throw `PermissionError` and the predictor crash-falls-back
to retraining. See Kai Learning **Part D.2**.

Drill deeper into the dir that matters:
```cmd
docker run --rm nba-pipeline:local ls -la /app/models
```
`bundles/` exists and is appuser-owned, ready for the S3 pull to populate it.

---

## Exercise 4 — confirm the heavy dependency is baked in

```cmd
docker run --rm nba-pipeline:local python -c "import torch; print(torch.__version__)"
```
Expect: **`2.9.1+cpu`** (the `+cpu` proves it's the CPU build from the dedicated
PyTorch index — no multi-GB CUDA payload, since Fargate has no GPU).

Contrast with the API image, which deliberately has **no** torch:
```cmd
docker run --rm nba-api:local python -c "import torch" 
```
Expect a `ModuleNotFoundError`. That "failure" is the SERVE-vs-COMPUTE split
working as designed — the public image stays tiny.

---

## Exercise 5 — the interactive shell (drive it yourself)

A real shell *inside* the frozen image (needs an interactive terminal, so run it
in your own cmd.exe — not through any automation):
```cmd
docker run --rm -it nba-pipeline:local bash
```
`-it` = interactive + TTY. Inside, try:
```sh
whoami                 # appuser
pwd                    # /app  (the WORKDIR)
ls -la /app            # ownership split again
python -c "import torch, sklearn, xgboost; print('all import OK')"
cat /etc/os-release     # Debian (the python:3.12-slim base)
exit                   # leave; --rm deletes the container
```
This is the fastest way to demystify "what's actually in there."

---

## Exercise 6 — chase the 3.19 GB `COPY . .` (a real optimization hunt)

`docker history` flagged the `COPY . .` layer at **3.19 GB** — far larger than
"just your code" should be. That means the **build context** (everything sent to
the daemon at build time) is dragging in big files that `.dockerignore` should
exclude. Investigate, evidence-first:

**Step A — what does `.dockerignore` currently strip?** (project root)
```cmd
type .dockerignore
```

**Step B — check the prime suspect** (the DB dump created during Week 2.4):
```cmd
dir infra\nba_data.sql
```
A multi-hundred-MB / GB `.sql` here that `.dockerignore` doesn't list would be
copied straight into the image.

**Step C — list other large files in the context** (>100 MB):
```cmd
forfiles /S /M * /C "cmd /c if @fsize GEQ 104857600 echo @fsize @path"
```
(Slow on big trees; Ctrl-C is fine. Anything big that isn't a dependency the
*pipeline* needs at runtime is bloat.)

**The fix when you find a culprit:** add it to `.dockerignore` (e.g. a line like
`infra/` or `*.sql`), rebuild, and re-check `docker history` — the `COPY . .`
layer should shrink dramatically. Smaller context = faster builds, smaller image,
faster ECR push, and a smaller attack surface.

> Note: `.dockerignore` ≠ `.gitignore`. They're separate files with the same
> syntax; Docker only reads `.dockerignore`. A file can be git-ignored but still
> sent into the build context (and vice-versa).

---

## Exercise 7 — "what breaks if I delete this line?" (break it on purpose)

The fastest teacher. Predict the failure first, then confirm:

1. **Remove the `chown` line** from `Dockerfile.pipeline`, rebuild, run the
   predictor → the `PermissionError` on `models/` returns (Part D.2).
2. **Remove `--host 0.0.0.0`** from `Dockerfile.api`'s `CMD`, rebuild, `docker run
   -p 8000:8000` → uvicorn binds to localhost *inside* the container, so it's
   unreachable from your host. (Restore it after.)
3. **Move `COPY . .` above the `pip install` lines** in the pipeline → now every
   code edit busts the 2.6 GB dependency cache and rebuilds are slow. This is the
   layer-ordering lesson, felt.

Always restore the file afterward (`git checkout -- Dockerfile.pipeline`).

---

## Command cheat sheet

| Command | What it shows |
|---|---|
| `docker images \| findstr nba` | which images exist + sizes |
| `docker history <img>` | layers + per-layer size (the build, reverse-engineered) |
| `docker run --rm <img> <cmd>` | run one command inside a throwaway container |
| `docker run --rm -it <img> bash` | interactive shell inside the image |
| `docker info` | is the engine up? |
| `docker ps` / `docker ps -a` | running / all containers |
| `docker inspect <img>` | full JSON: env, entrypoint, layers, user |

---

## The takeaways

- **Layers = the build, frozen.** `docker history` lets you read any image's
  Dockerfile backwards, with sizes.
- **The container is just your code in a box you can open.** `docker run … <cmd>`
  and `-it bash` remove all the mystery.
- **Constraint → line.** Every Dockerfile decision traces back to the job's needs
  (SERVE stays tiny; COMPUTE carries the heavy deps).
- **Measure, don't guess.** `docker history` surfaced a real 3.19 GB problem we'd
  never have spotted by reading the Dockerfile alone.
