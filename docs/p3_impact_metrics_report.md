# P3 — Prior-season Estimated RAPTOR as a player-projection feature

Arms: baseline (current P2 features, incl. PIE_L10/USG_PCT_L10) vs +PREV_ERAPTOR_{OFF,DEF,TOT,WAR82} (previous-season Estimated RAPTOR, minutes-weighted across stints, matched by normalized name — point-in-time safe by construction).

Match rate by season: {'22022': 0.8753, '22023': 0.8761, '22024': 0.8747, '22025': 0.8754}

| Stat | mean ΔMAE (aug−base) | seeds passing all folds (of 3) | keep? |
|---|---|---|---|
| MIN | -0.0013 | 0 | no |
| PTS | -0.0068 | 0 | no |
| REB | -0.0004 | 0 | no |
| AST | -0.0000 | 0 | no |
| STL | -0.0003 | 0 | no |
| BLK | +0.0007 | 0 | no |
| TOV | -0.0000 | 0 | no |
| FG3M | -0.0001 | 0 | no |
| FG3A | -0.0004 | 0 | no |
| FTM | -0.0002 | 0 | no |
| FTA | -0.0002 | 0 | no |

Negative ΔMAE = the eRAPTOR features improved that stat. Gate: delta < 0 AND p < 0.05 in all three folds, for ≥2 of 3 seeds (per the noise-aware eval policy).

Per-run detail in `outputs/p3_impact_metrics.json` (per fold/seed: MAE both arms, paired-t, and the gain-rank of each new feature in the augmented MIN and PTS models).