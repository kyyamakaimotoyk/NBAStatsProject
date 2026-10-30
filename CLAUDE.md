# CLAUDE.md

NBA game + player prediction project behind hoopmodel.com (local research bench +
AWS deployment). Owner: Kai.

## Navigating the docs (context-efficient)
1. `docs/INDEX.md`: which doc is canonical for what, its status and size.
2. `docs/CHANGELOG.md`: dated recent changes, each linking to its write-up.
3. Then read only the sections you need. `docs/model_tuning_log.md` (~2,000 lines)
   and `docs/aws_deployment_plan.md` (~1,400) are for grepping, not reading whole:
   `grep -n "^## 20" docs/model_tuning_log.md` lists every experiment.

## Rules
- Tuning log is append-only; correct past entries with a dated inline note.
- After any change that alters the model, data, public site or a recorded decision,
  add a line to `docs/CHANGELOG.md` (and the tuning log for model/eval changes).
- Feature and model changes need multi-seed + paired tests before they're kept (E12).
- Public content (site, articles, API) never discloses feature lists/counts,
  hyperparameters or pipeline internals (`docs/articles.md` "Disclosure line").
- DB writes (local MySQL, RDS), terraform applies and image pushes are Kai's to
  run: write the exact commands down (usually `docs/preseason_checklist.md`).
- `.bat` files need CRLF; `requirements*.txt` must be ASCII (cp932 locale).
