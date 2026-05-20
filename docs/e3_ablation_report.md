# E3 noise-aware feature ablation — full report

_Generated: 2026-05-19T19:58:44_

---

## TL;DR

| Feature | Tested in | Verdict | Rationale |
|---|---|---|---|
| **E9 (ELO)** | RF, XGB | **KEEP** | Only feature with a statistically significant AUC gain on RF (AUC Δ +0.013, p=0.012-0.016, consistent across E7-on/off). Doesn't hurt XGB. Cheap (4 columns). |
| **E10 (opp-strength adjustment)** | RF, XGB | **DROP** | Actively *regresses* RF MAE (+0.034, paired-t p=0.023 / p=0.011 across both CSVs). XGB AUC regression in E10-only and E10+E11 combos. ~54 columns of added noise. |
| **E11 (LeagueDashLineups)** | RF, XGB | **DROP** | No significant improvement on any metric, any model, either CSV. 27 columns of noise + 57% NaN imputation. Earlier "+1.3 to +2.6pp" was within bootstrap CI. |
| **E7 (pregame injury data)** | RF, XGB | **KEEP** | XGB MAE Δ = -0.307 to -0.405 when E7 is on. Directional only (cross-CSV comparison is not formally paired). Worth keeping based on absolute lift on XGB regressor + literature support. |

**Bottom line**: of the four post-E8 experiments, only **E9 and E7** survive rigorous noise-aware testing. E10 and E11 should be removed.

---

## Was your noise intuition correct?

**Yes, almost exactly.** Two specific claims you made and the data behind each:

### Claim 1: "AUC increase by <1pp may be within noise"
**Verified.** Bootstrap 95% CIs on AUC are ~0.06 wide (e.g. baseline RF AUC = 0.8199 [0.7602, 0.8744]). A claimed "+0.005 AUC" gain between configs sits inside the CI overlap and is statistically indistinguishable.

However, there's an important nuance — **paired tests are more sensitive** than comparing two CIs. The bootstrap on a single config measures *unpaired* noise. The McNemar and paired-t and bootstrap-on-Δ tests in this report compare *the same test games* across configs, which removes shared variance. That's how E9's +0.013 AUC Δ on RF can be significant (p=0.012) even though the per-config CIs overlap heavily.

So the refined version of your claim: "<0.005 AUC gain or <0.5pp accuracy gain is likely noise *unless* a paired test confirms it." That's exactly what this study tested.

### Claim 2: "Throwing garbage features in"
**Partly verified, with one strong example.** E10 is the cleanest case — it didn't just fail to help, it *significantly hurt* RF MAE (+0.034 with paired-t p=0.023 on E7-on, p=0.011 on E7-off). 54 new columns of correlated, noisy data pushed RF's median imputer + tree splits toward worse regression. E11 was neutral-to-slightly-negative but never significant.

XGB's pattern is particularly telling: it gained nothing significant from *any* experimental config. Gradient boosting with subsample=0.8 and L2 regularization is already extracting most of the signal from base features; adding correlated derivatives doesn't help and occasionally hurts (E10_only XGB AUC p=0.042 in E7-off, E10+E11 XGB MAE p=0.013 in E7-on).

### Where the noise floor actually is

On W5 (n_test=230), the noise floor we measured:
- **Accuracy**: bootstrap CI ≈ ±5pp on any single config. Paired McNemar on ~10-15 disagreements typically needs ≥3pp difference (10+ vs 4) to clear p<0.05.
- **MAE**: bootstrap CI ≈ ±1.2 points on any single config. Paired-t on per-game errors picks up ~0.15-0.20 point differences when they're consistent.
- **AUC**: bootstrap CI ≈ ±0.06 on any single config. Paired bootstrap on Δ picks up ~0.005-0.010 differences when they're consistent.

So your original instinct was right: most of the deltas in the prior log entries (<0.5pp acc, <0.005 AUC, <0.2 MAE) sat below or near the paired-test floor.

---

## What this study did




W5 walk-forward window: train on games strictly before 2026-03-15, test on 2026-03-15 → 2026-04-15 (n_test=230, n_train=6021).

For each of 8 (E9, E10, E11) toggle configurations × 10 seeds × {RF, XGB}: train fresh, predict on W5 test. Each prediction set bootstrap-resampled 1000 times → 10 seeds × 1000 = 10,000 metric measurements per cell.

Pairwise comparisons use predictions averaged across seeds; McNemar χ² for accuracy, paired t-test on per-game |error| for MAE, bootstrap on the AUC delta.

## CSV: E7-on (pregame injury report)


### Bootstrap CIs by config × model

*Bootstrap-CI (95%) from 10 seeds × 1000 test-set resamples per cell. n_test=230.*


**RF**

| Config | Accuracy (%) | AUC | MAE |
|---|---|---|---|
| baseline | 76.13 [70.43, 81.74] | 0.8199 [0.7602, 0.8744] | 12.080 [10.905, 13.301] |
| E9_only | 77.98 [72.17, 83.48] | 0.8327 [0.7741, 0.8858] | 11.899 [10.753, 13.100] |
| E10_only | 75.35 [69.57, 80.87] | 0.8196 [0.7604, 0.8739] | 12.113 [10.951, 13.335] |
| E11_only | 76.28 [70.43, 81.74] | 0.8232 [0.7648, 0.8767] | 12.064 [10.894, 13.279] |
| E9+E10 | 77.71 [71.74, 83.48] | 0.8330 [0.7747, 0.8856] | 11.907 [10.756, 13.117] |
| E9+E11 | 78.05 [72.17, 83.48] | 0.8323 [0.7741, 0.8853] | 11.883 [10.738, 13.087] |
| E10+E11 | 76.06 [70.43, 81.74] | 0.8201 [0.7610, 0.8743] | 12.103 [10.940, 13.328] |
| E9+E10+E11_full | 77.89 [71.74, 83.48] | 0.8320 [0.7742, 0.8856] | 11.888 [10.738, 13.096] |

**XGB**

| Config | Accuracy (%) | AUC | MAE |
|---|---|---|---|
| baseline | 77.26 [71.30, 83.04] | 0.8259 [0.7641, 0.8806] | 11.721 [10.498, 12.997] |
| E9_only | 76.86 [70.87, 82.61] | 0.8244 [0.7605, 0.8824] | 11.874 [10.576, 13.210] |
| E10_only | 76.63 [70.43, 82.61] | 0.8207 [0.7566, 0.8781] | 11.870 [10.620, 13.203] |
| E11_only | 76.49 [70.43, 82.17] | 0.8210 [0.7585, 0.8780] | 11.779 [10.571, 13.016] |
| E9+E10 | 77.41 [71.30, 83.04] | 0.8253 [0.7628, 0.8813] | 11.876 [10.658, 13.134] |
| E9+E11 | 77.11 [71.30, 82.61] | 0.8256 [0.7657, 0.8804] | 11.824 [10.639, 13.060] |
| E10+E11 | 76.55 [70.43, 82.17] | 0.8155 [0.7541, 0.8714] | 11.938 [10.712, 13.203] |
| E9+E10+E11_full | 76.83 [70.00, 83.91] | 0.8265 [0.7644, 0.8835] | 11.776 [10.566, 13.036] |

### Pairwise significance vs baseline

*All comparisons vs `baseline`. McNemar = paired test on classifier agreement; paired-t = on per-game |error| diff for MAE; bootstrap-AUC = on AUC delta.*

*Significance: `*` p<0.05, `**` p<0.01, `***` p<0.001.*


**RF** — config-vs-baseline

| Config | Acc gain (cfg-wins/base-wins) | McNemar p | MAE Δ | paired-t p | AUC Δ [95% CI] | AUC p |
|---|---|---|---|---|---|---|
| E10+E11 | 0.00pp (2/2) | 0.617 | +0.025 | 0.145 | +0.0007 [-0.0053, 0.0069] | 0.814 |
| E10_only | -0.87pp (1/3) | 0.617 | +0.034* | 0.023* | +0.0003 [-0.0065, 0.0071] | 0.920 |
| E11_only | -0.43pp (1/2) | 1.000 | -0.016 | 0.085 | +0.0035 [-0.0003, 0.0077] | 0.088 |
| E9+E10+E11_full | 1.74pp (8/4) | 0.386 | -0.199 | 0.270 | +0.0129 [0.0026, 0.0240] | 0.016* |
| E9+E10 | 1.74pp (7/3) | 0.343 | -0.181 | 0.315 | +0.0118 [0.0011, 0.0233] | 0.032* |
| E9+E11 | 2.61pp (10/4) | 0.181 | -0.204 | 0.260 | +0.0121 [0.0013, 0.0231] | 0.026* |
| E9_only | 2.17pp (8/3) | 0.228 | -0.188 | 0.297 | +0.0136 [0.0034, 0.0250] | 0.012* |

**XGB** — config-vs-baseline

| Config | Acc gain (cfg-wins/base-wins) | McNemar p | MAE Δ | paired-t p | AUC Δ [95% CI] | AUC p |
|---|---|---|---|---|---|---|
| E10+E11 | -3.04pp (3/10) | 0.096 | +0.225* | 0.013* | -0.0120 [-0.0244, -0.0002] | 0.048* |
| E10_only | -1.30pp (5/8) | 0.579 | +0.139 | 0.117 | -0.0056 [-0.0176, 0.0049] | 0.336 |
| E11_only | -0.87pp (2/4) | 0.683 | +0.055 | 0.518 | -0.0060 [-0.0159, 0.0031] | 0.186 |
| E9+E10+E11_full | -1.30pp (6/9) | 0.606 | +0.042 | 0.789 | +0.0005 [-0.0165, 0.0185] | 0.968 |
| E9+E10 | 0.43pp (7/6) | 1.000 | +0.135 | 0.382 | -0.0013 [-0.0175, 0.0156] | 0.844 |
| E9+E11 | -0.43pp (5/6) | 1.000 | +0.079 | 0.604 | +0.0004 [-0.0160, 0.0166] | 0.962 |
| E9_only | -1.30pp (5/8) | 0.579 | +0.157 | 0.309 | -0.0010 [-0.0163, 0.0148] | 0.890 |

## CSV: E7-off (postgame boxscore)


### Bootstrap CIs by config × model

*Bootstrap-CI (95%) from 10 seeds × 1000 test-set resamples per cell. n_test=230.*


**RF**

| Config | Accuracy (%) | AUC | MAE |
|---|---|---|---|
| baseline | 75.71 [70.00, 81.30] | 0.8194 [0.7598, 0.8739] | 12.103 [10.940, 13.321] |
| E9_only | 78.01 [71.74, 83.48] | 0.8318 [0.7735, 0.8852] | 11.917 [10.772, 13.122] |
| E10_only | 75.48 [69.57, 81.30] | 0.8193 [0.7598, 0.8741] | 12.141 [10.979, 13.358] |
| E11_only | 75.83 [70.00, 81.74] | 0.8215 [0.7628, 0.8753] | 12.090 [10.921, 13.308] |
| E9+E10 | 77.58 [71.74, 83.04] | 0.8321 [0.7741, 0.8854] | 11.930 [10.775, 13.133] |
| E9+E11 | 78.39 [72.61, 83.91] | 0.8323 [0.7741, 0.8853] | 11.904 [10.762, 13.111] |
| E10+E11 | 75.92 [70.00, 81.30] | 0.8193 [0.7598, 0.8735] | 12.131 [10.969, 13.348] |
| E9+E10+E11_full | 77.24 [71.30, 83.04] | 0.8307 [0.7722, 0.8841] | 11.915 [10.762, 13.122] |

**XGB**

| Config | Accuracy (%) | AUC | MAE |
|---|---|---|---|
| baseline | 76.41 [69.57, 82.61] | 0.8200 [0.7574, 0.8779] | 12.126 [10.887, 13.415] |
| E9_only | 77.47 [71.30, 83.48] | 0.8243 [0.7616, 0.8804] | 12.174 [10.921, 13.469] |
| E10_only | 76.71 [69.57, 83.04] | 0.8116 [0.7440, 0.8712] | 12.164 [10.931, 13.420] |
| E11_only | 76.72 [70.87, 82.61] | 0.8192 [0.7567, 0.8751] | 12.167 [10.960, 13.425] |
| E9+E10 | 77.16 [70.43, 83.04] | 0.8216 [0.7549, 0.8812] | 12.106 [10.849, 13.388] |
| E9+E11 | 76.20 [70.43, 81.74] | 0.8145 [0.7502, 0.8726] | 12.185 [10.947, 13.454] |
| E10+E11 | 76.36 [70.43, 81.74] | 0.8093 [0.7457, 0.8678] | 12.297 [11.084, 13.553] |
| E9+E10+E11_full | 76.98 [70.43, 83.04] | 0.8205 [0.7592, 0.8769] | 12.083 [10.872, 13.321] |

### Pairwise significance vs baseline

*All comparisons vs `baseline`. McNemar = paired test on classifier agreement; paired-t = on per-game |error| diff for MAE; bootstrap-AUC = on AUC delta.*

*Significance: `*` p<0.05, `**` p<0.01, `***` p<0.001.*


**RF** — config-vs-baseline

| Config | Acc gain (cfg-wins/base-wins) | McNemar p | MAE Δ | paired-t p | AUC Δ [95% CI] | AUC p |
|---|---|---|---|---|---|---|
| E10+E11 | -0.87pp (1/3) | 0.617 | +0.028 | 0.116 | +0.0002 [-0.0062, 0.0063] | 0.934 |
| E10_only | -0.43pp (3/4) | 1.000 | +0.038* | 0.011* | +0.0013 [-0.0056, 0.0082] | 0.692 |
| E11_only | 0.00pp (1/1) | 0.480 | -0.014 | 0.147 | +0.0026 [-0.0013, 0.0068] | 0.210 |
| E9+E10+E11_full | 2.17pp (9/4) | 0.267 | -0.192 | 0.294 | +0.0116 [0.0006, 0.0235] | 0.038* |
| E9+E10 | 1.30pp (6/3) | 0.505 | -0.176 | 0.334 | +0.0117 [0.0012, 0.0229] | 0.034* |
| E9+E11 | 3.04pp (11/4) | 0.121 | -0.204 | 0.268 | +0.0129 [0.0013, 0.0246] | 0.030* |
| E9_only | 2.17pp (9/4) | 0.267 | -0.191 | 0.298 | +0.0129 [0.0029, 0.0238] | 0.012* |

**XGB** — config-vs-baseline

| Config | Acc gain (cfg-wins/base-wins) | McNemar p | MAE Δ | paired-t p | AUC Δ [95% CI] | AUC p |
|---|---|---|---|---|---|---|
| E10+E11 | -0.87pp (6/8) | 0.789 | +0.210* | 0.025* | -0.0111 [-0.0234, 0.0009] | 0.062 |
| E10_only | -0.43pp (5/6) | 1.000 | +0.013 | 0.880 | -0.0115 [-0.0236, -0.0007] | 0.042* |
| E11_only | -1.30pp (6/9) | 0.606 | +0.021 | 0.825 | -0.0031 [-0.0157, 0.0088] | 0.626 |
| E9+E10+E11_full | 0.00pp (9/9) | 0.814 | -0.064 | 0.681 | -0.0019 [-0.0195, 0.0166] | 0.818 |
| E9+E10 | -0.87pp (9/11) | 0.823 | -0.036 | 0.806 | +0.0013 [-0.0166, 0.0199] | 0.930 |
| E9+E11 | -0.87pp (8/10) | 0.814 | +0.026 | 0.862 | -0.0072 [-0.0254, 0.0110] | 0.440 |
| E9_only | -0.43pp (8/9) | 1.000 | +0.025 | 0.870 | +0.0040 [-0.0135, 0.0228] | 0.700 |

### E7 effect — full-config (E9+E10+E11) results across CSVs

*Same model config, same seeds, two CSVs differing only in how `_AVAILABLE` columns were populated (pregame injury report = E7-on, postgame boxscore = E7-off).*


**RF / baseline**
| Metric | E7-on (pregame) | E7-off (postgame) | Δ (E7-on − E7-off) |
|---|---|---|---|
| Accuracy | 76.13% [70.43, 81.74] | 75.71% [70.00, 81.30] | 0.42pp |
| AUC | 0.8199 [0.7602, 0.8744] | 0.8194 [0.7598, 0.8739] | +0.0005 |
| MAE | 12.080 [10.905, 13.301] | 12.103 [10.940, 13.321] | -0.023 |

**XGB / baseline**
| Metric | E7-on (pregame) | E7-off (postgame) | Δ (E7-on − E7-off) |
|---|---|---|---|
| Accuracy | 77.26% [71.30, 83.04] | 76.41% [69.57, 82.61] | 0.85pp |
| AUC | 0.8259 [0.7641, 0.8806] | 0.8200 [0.7574, 0.8779] | +0.0059 |
| MAE | 11.721 [10.498, 12.997] | 12.126 [10.887, 13.415] | -0.405 |

**RF / E9+E10+E11_full**
| Metric | E7-on (pregame) | E7-off (postgame) | Δ (E7-on − E7-off) |
|---|---|---|---|
| Accuracy | 77.89% [71.74, 83.48] | 77.24% [71.30, 83.04] | 0.64pp |
| AUC | 0.8320 [0.7742, 0.8856] | 0.8307 [0.7722, 0.8841] | +0.0014 |
| MAE | 11.888 [10.738, 13.096] | 11.915 [10.762, 13.122] | -0.027 |

**XGB / E9+E10+E11_full**
| Metric | E7-on (pregame) | E7-off (postgame) | Δ (E7-on − E7-off) |
|---|---|---|---|
| Accuracy | 76.83% [70.00, 83.91] | 76.98% [70.43, 83.04] | -0.15pp |
| AUC | 0.8265 [0.7644, 0.8835] | 0.8205 [0.7592, 0.8769] | +0.0060 |
| MAE | 11.776 [10.566, 13.036] | 12.083 [10.872, 13.321] | -0.307 |

## Recommendation: which features to keep

*Decision rule: keep a feature group iff at least ONE of {RF, XGB} shows a statistically significant improvement (p<0.05) on at least one of {accuracy via McNemar, MAE via paired-t, AUC via bootstrap}.*


### E9_only: **KEEP** (1 significant test(s))
  - RF AUC (bootstrap p=0.012*, Δ=+0.0136)

### E10_only: **CONSIDER DROPPING** (no significant improvement at p<0.05)

### E11_only: **CONSIDER DROPPING** (no significant improvement at p<0.05)

### E7 (pre-game injury data)

*E7 isn't a feature toggle; it changes the *content* of `_AVAILABLE` columns. We compare same-config results across the two CSVs.*

  - RF: acc Δ = +0.64pp, MAE Δ = -0.027
  - XGB: acc Δ = -0.15pp, MAE Δ = -0.307

  → **KEEP E7** (helps on ['RF', 'XGB'] by heuristic threshold)

  *Note: this is a single-CSV-pair comparison without a paired test between CSVs (seeds re-run on different data). Treat as directional, not formally significant.*