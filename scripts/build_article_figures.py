"""Build the data behind the figures in /articles.

Reads experiment outputs (outputs/*.json, the frozen features snapshot) and the
live public API, and writes one small JSON per article to web/data/articles/.
Only aggregated, publishable numbers go out: no feature names, no
hyperparameters, no column counts (see the disclosure line in docs/articles.md).
The web bundle is public, so everything written here is published.

    python scripts/build_article_figures.py            # all articles
    python scripts/build_article_figures.py margin-floor

Re-run right before publishing or refreshing an article, then check the
numbers quoted in the article text still match the figures.
"""

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
DEST = ROOT / "web" / "data" / "articles"
API = "https://api.hoopmodel.com"

PLAYER_STATS = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG3A", "FTM", "FTA"]


def load(name):
    return json.loads((OUT / name).read_text())


def r(x, nd=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def write(slug, payload):
    DEST.mkdir(parents=True, exist_ok=True)
    payload = {"generated": date.today().isoformat(), **payload}
    (DEST / f"{slug}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote web/data/articles/{slug}.json")


# --- signal-or-noise -------------------------------------------------------

def signal_or_noise():
    e3 = load("e3_ablation_e7on.json")
    s, paired = e3["summary"], e3["paired"]
    # Article names for the ablation configs (E9 = Elo, E10 = opponent-adjusted,
    # E11 = lineup stats); only single-group configs are shown.
    configs = [("baseline", "base"), ("E9_only", "elo"), ("E10_only", "oppadj"), ("E11_only", "lineup")]
    ranges = []
    for cfg, key in configs:
        for m in ("RF", "XGB"):
            a = s[f"{cfg}|{m}|acc"]
            ranges.append({"config": key, "model": m.lower(), "mean": r(a["mean"] * 100, 1),
                           "lo": r(a["ci_lo"] * 100, 1), "hi": r(a["ci_hi"] * 100, 1)})

    splits = []
    for cfg, key in configs[1:]:
        for m in ("RF", "XGB"):
            p = paired[f"{cfg}|{m}"]
            splits.append({"change": key, "model": m.lower(), "new": p["cfg_wins"],
                           "old": p["base_wins"], "p": r(p["mcnemar_p"], 2)})
    e24 = load("e24_w5.json")["windows"]["W5"]["paired"]["xgb_tuned|XGB"]
    splits.append({"change": "tuning", "model": "xgb", "new": e24["cfg_wins"],
                   "old": e24["base_wins"], "p": r(e24["mcnemar_p"], 2)})

    # Player tuning (P7, every stat on tuned settings): % change in MAE per stat,
    # averaged over folds x seeds; min/max across runs as the range.
    p7 = load("p7_gate.json")
    arm = [a for a in p7["arms_resolved"] if a != "baseline"][0]
    per = {st: [] for st in PLAYER_STATS}
    fp = []
    for run in p7["runs"]:
        base, tuned = run["arms"]["baseline"], run["arms"][arm]
        for st in PLAYER_STATS:
            per[st].append((tuned["mae"][st] - base["mae"][st]) / base["mae"][st] * 100)
        fp.append((tuned["fp_mae"] - base["fp_mae"]) / base["fp_mae"] * 100)
    verdicts = p7["verdicts"][arm]["per_stat"]
    tuning = [{"stat": st, "pct": r(np.mean(v), 2), "lo": r(min(v), 2), "hi": r(max(v), 2),
               "keep": bool(verdicts[st]["keep"])}
              for st, v in per.items()]
    write("signal-or-noise", {
        "source": "Feature ablation, 10 seeds x 1,000 resamples of a 230-game test month; tuning check on a held-out month; player tuning over 3 seasons x 3 seeds.",
        "n_test": e3["n_test"],
        "ranges": ranges,
        "splits": splits,
        "player_tuning": tuning,
        "player_tuning_fp": {"pct": r(np.mean(fp), 2), "lo": r(min(fp), 2), "hi": r(max(fp), 2)},
    })


_RESULTS = None


def api_results():
    """Every graded prediction on the public track record (one row per game x model)."""
    global _RESULTS
    if _RESULTS is None:
        with urllib.request.urlopen(f"{API}/api/performance/results?days=1100", timeout=60) as f:
            _RESULTS = pd.DataFrame(json.load(f)["results"])
    return _RESULTS.copy()


# --- margin-floor ----------------------------------------------------------

def margin_floor():
    df = api_results()
    df = df[df["actual_margin"].notna()]
    games = df.drop_duplicates("game_id")
    m = games["actual_margin"].astype(float)

    # One bar per point of margin; tails beyond +-40 fold into the end bars.
    clipped = m.clip(-40, 40).round().astype(int)
    counts = clipped.value_counts()
    hist = [{"x": x, "pct": r(counts.get(x, 0) / len(m) * 100, 2), "n": int(counts.get(x, 0))}
            for x in range(-40, 41)]

    # Average miss on games that have a closing line, so every bar is scored on
    # the same games.
    lined = games[games["market_margin"].notna()]
    lined_ids = set(lined["game_id"])
    miss = [{"key": "naive", "mae": r((lined["actual_margin"] - 2).abs().mean(), 2), "n": len(lined)}]
    model_errs = {}
    for mt in ("rf", "nn", "xgb"):
        sub = df[(df["model_type"] == mt) & df["game_id"].isin(lined_ids) & df["predicted_margin"].notna()]
        sub = sub.drop_duplicates("game_id")
        # predicted_margin is the winner's margin; sign it home-positive
        signed = np.where(sub["predicted_winner"] == sub["home_team"], sub["predicted_margin"].abs(), -sub["predicted_margin"].abs())
        err = (signed - sub["actual_margin"]).abs()
        model_errs[mt] = err.to_numpy()
        miss.append({"key": mt, "mae": r(err.mean(), 2), "n": len(sub)})
    mkt_err = (lined["market_margin"] - lined["actual_margin"]).abs().to_numpy()
    miss.append({"key": "market", "mae": r(mkt_err.mean(), 2), "n": len(lined)})

    xs = list(range(0, 31))
    all_model = np.concatenate(list(model_errs.values()))
    within = [{"x": x,
               "market": r((mkt_err <= x).mean() * 100, 1),
               "models": r((all_model <= x).mean() * 100, 1)} for x in xs]
    write("margin-floor", {
        "source": "Every graded game on the track record (public API).",
        "from": games["game_date"].min(),
        "to": games["game_date"].max(),
        "n_games": len(games),
        "n_lined": len(lined),
        "margin_sd": r(m.std(), 1),
        "margin_median_abs": r(m.abs().median(), 1),
        "share_within5_actual": r((m.abs() <= 5).mean() * 100, 1),
        "share_20plus": r((m.abs() >= 20).mean() * 100, 1),
        "hist": hist,
        "miss": miss,
        "within": within,
        "model_p50": r(np.percentile(all_model, 50), 1),
        "model_p80": r(np.percentile(all_model, 80), 1),
    })


# --- impact-ratings --------------------------------------------------------

def impact_ratings():
    p3 = load("p3_impact_metrics.json")
    per = {st: [] for st in PLAYER_STATS}
    for run in p3["runs"]:
        for st in PLAYER_STATS:
            x = run["stats"][st]
            per[st].append(x["delta_mae"] / x["mae_base"] * 100)
    player = [{"stat": st, "pct": r(np.mean(v), 3), "lo": r(min(v), 3), "hi": r(max(v), 3)}
              for st, v in per.items()]

    # Standalone signal: home win rate by prior-season rating gap (quintiles).
    cols = pd.read_csv(OUT / "e25_eraptor_team_cols.csv", usecols=["GAME_ID", "DIFF_ERAPTOR_TOT_WMEAN"])
    feats = pd.read_csv(ROOT / "nba_ml_features_frozen.csv", usecols=["GAME_ID", "HOME_WIN", "HOME_PLUS_MINUS"])
    j = cols.merge(feats, on="GAME_ID").dropna()
    corr = j["DIFF_ERAPTOR_TOT_WMEAN"].corr(j["HOME_PLUS_MINUS"])
    j["q"] = pd.qcut(j["DIFF_ERAPTOR_TOT_WMEAN"], 5, labels=False)
    buckets = [{"q": int(q) + 1, "win_pct": r(g["HOME_WIN"].mean() * 100, 1), "n": len(g)}
               for q, g in j.groupby("q")]
    pos = j[j["DIFF_ERAPTOR_TOT_WMEAN"] > 0]

    # In-model: paired differences (with CIs) on the held-out month and pooled
    # over the monthly windows.
    inmodel = []
    for stage, f in (("month", "e25_w5.json"), ("pooled", "e25_windows.json")):
        d = load(f)
        paired = d["windows"]["W5"]["paired"] if stage == "month" else d["pooled"]["paired"]
        n = d["windows"]["W5"]["n_test"] if stage == "month" else d["pooled"]["n_test"]
        for m in ("RF", "XGB"):
            p = paired[f"aug_eraptor|{m}"]
            inmodel.append({"stage": stage, "model": m.lower(), "n": n,
                            "auc": r(p["auc_diff_mean"], 4), "auc_lo": r(p["auc_diff_ci_lo"], 4), "auc_hi": r(p["auc_diff_ci_hi"], 4),
                            "mae": r(p["mae_diff_mean"], 3), "mae_lo": r(p.get("mae_diff_ci_lo"), 3), "mae_hi": r(p.get("mae_diff_ci_hi"), 3)})
    write("impact-ratings", {
        "source": "Player model: 3 seasons x 3 seeds. Team model: 2022-2026 games with a prior-season rating for both sides; in-model tests on a held-out month and 21 monthly windows.",
        "player": player,
        "team_corr": r(corr, 2),
        "team_pos_win_pct": r(pos["HOME_WIN"].mean() * 100, 1),
        "team_n": len(j),
        "buckets": buckets,
        "inmodel": inmodel,
    })


# --- playoff-predictability ------------------------------------------------

def playoff_predictability():
    reg = load("e15_regime.json")["pooled"]
    metrics = []
    for m in ("RF", "XGB"):
        for phase in ("regular", "playoffs"):
            x = reg[m][phase]
            metrics.append({"model": m.lower(), "phase": phase, "n": x["n"],
                            "acc": r(x["acc"] * 100, 1), "auc": r(x["auc"], 3),
                            "cov90": r(x["cov90"] * 100, 1), "mae": r(x["mae"], 1)})

    # How lopsided are the matchups? Elo favourite's pre-game win probability,
    # last 21 days of each regular season vs that season's playoffs.
    f = pd.read_csv(ROOT / "nba_ml_features_frozen.csv", usecols=["GAME_ID", "GAME_DATE", "ELO_P_HOME"])
    f["GAME_DATE"] = pd.to_datetime(f["GAME_DATE"])
    f["kind"] = f["GAME_ID"].astype(str).str.zfill(10).str[2]  # 2 regular, 4 playoffs, 5 play-in
    f["fav"] = np.maximum(f["ELO_P_HOME"], 1 - f["ELO_P_HOME"])
    groups = {"regular": [], "playoffs": []}
    for yr, po in f[f["kind"] == "4"].groupby(f["GAME_DATE"].dt.year):
        start = po["GAME_DATE"].min()
        rs = f[(f["kind"] == "2") & (f["GAME_DATE"] < start) & (f["GAME_DATE"] >= start - pd.Timedelta(days=35))]
        rs = rs[rs["GAME_DATE"] >= rs["GAME_DATE"].max() - pd.Timedelta(days=20)]
        groups["regular"].append(rs["fav"])
        groups["playoffs"].append(po["fav"])
    edges = [0.5, 0.6, 0.7, 0.8, 1.0001]
    labels = ["50-60", "60-70", "70-80", "80+"]
    fav = []
    for phase, parts in groups.items():
        v = pd.concat(parts).dropna()
        c, _ = np.histogram(v, bins=edges)
        for lab, k in zip(labels, c):
            fav.append({"phase": phase, "bucket": lab, "pct": r(k / len(v) * 100, 1), "n": int(k)})
        fav.append({"phase": phase, "bucket": "median", "pct": r(v.median() * 100, 1), "n": len(v)})
    write("playoff-predictability", {
        "source": "Five seasons (2022-2026); models trained on regular-season games before each season's playoffs, 5 seeds.",
        "metrics": metrics,
        "favourite": fav,
    })


# --- early-season ----------------------------------------------------------

MONTHS = [(10, "Oct"), (11, "Nov"), (12, "Dec"), (1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr")]


def early_season():
    df = api_results()
    # Regular season only (GAME_ID type digit 2), graded, with a non-pick'em
    # closing line so models and market are scored on the same games.
    df = df[(df["game_id"].str[2] == "2") & df["is_correct"].notna()
            & df["market_margin"].notna() & (df["market_margin"] != 0)].copy()
    df["season"] = df["game_id"].str[3:5]
    df["month"] = pd.to_datetime(df["game_date"]).dt.month
    home_won = df["actual_winner"] == df["home_team"]
    df["market_correct"] = (df["market_margin"] > 0) == home_won
    df["spread"] = df["market_margin"].abs()
    current = df["season"].max()
    past, cur = df[df["season"] != current], df[df["season"] == current]
    past_games = past.drop_duplicates("game_id")

    months = []
    for m, label in MONTHS:
        rows, games = past[past["month"] == m], past_games[past_games["month"] == m]
        if games.empty:
            continue
        by_model = rows.groupby("model_type")["is_correct"].mean()
        months.append({
            "m": label, "games": len(games),
            "models": r(rows["is_correct"].mean() * 100, 1),
            "market": r(games["market_correct"].mean() * 100, 1),
            **{k: r(by_model.get(k, np.nan) * 100, 1) for k in ("rf", "nn", "xgb")},
            "spread": r(games["spread"].mean(), 1),
            "spread8": r((games["spread"] >= 8).mean() * 100, 1),
        })
    seasons = sorted(past["season"].unique())
    cur_games = cur.drop_duplicates("game_id")

    # Learning curve (E15 Q1): fixed March test month, growing training history.
    # The CI is the binomial interval for one test month, the dominant noise source.
    lc = load("e15_learning_curve.json")
    n_test = lc["n_test"]
    curve = []
    for i, pt in enumerate(lc["points"]):
        for m in ("RF", "XGB"):
            p = pt["models"][m]["acc"]["mean"]
            half = 1.96 * np.sqrt(p * (1 - p) / n_test)
            curve.append({"step": i, "n_train": pt["n_train"], "model": m.lower(),
                          "acc": r(p * 100, 1), "lo": r((p - half) * 100, 1), "hi": r((p + half) * 100, 1)})
    write("early-season", {
        "source": "Public track record, regular season, games with a closing line.",
        "seasons": [f"20{s}-{int(s) + 1}" for s in seasons],
        "from": past["game_date"].min(),
        "to": past["game_date"].max(),
        "n_games": len(past_games),
        "months": months,
        "current": {"season": f"20{current}-{int(current) + 1}", "games": len(cur_games),
                    "from": cur["game_date"].min(), "to": cur["game_date"].max(),
                    "models": r(cur["is_correct"].mean() * 100, 1),
                    "market": r(cur_games["market_correct"].mean() * 100, 1),
                    "spread": r(cur_games["spread"].mean(), 1)},
        "curve_n_test": n_test,
        "curve": curve,
    })


# --- calibration -----------------------------------------------------------

def calibration():
    # (1) Reliability on the E13 test month: predicted vs observed home-win rate.
    e13 = load("e13_calibration.json")
    rf = e13["models"]["RF"]
    reliability = [{"pred": r(b["mean_pred"] * 100, 1), "obs": r(b["obs_rate"] * 100, 1), "n": b["n"]}
                   for b in rf["raw"]["bins"]]

    # (2) Live 2025-26: who did each model pick, month by month (public API).
    df = api_results()
    df = df[(df["game_id"].str[2] == "2") & df["is_correct"].notna()].copy()
    df["season"] = df["game_id"].str[3:5]
    df["month"] = pd.to_datetime(df["game_date"]).dt.month
    df["home_pick"] = df["predicted_winner"] == df["home_team"]
    df["home_won"] = df["actual_winner"] == df["home_team"]

    def season_month(season):
        s = df[df["season"] == season]
        out = []
        for m, label in MONTHS:
            rows = s[s["month"] == m]
            if rows.empty:
                continue
            games = rows.drop_duplicates("game_id")
            lined = games[games["market_margin"].notna() & (games["market_margin"] != 0)]
            share = rows.groupby("model_type")["home_pick"].mean()
            acc = rows.groupby("model_type")["is_correct"].mean()
            out.append({
                "m": label, "games": len(games),
                **{k: r(share.get(k, np.nan) * 100, 1) for k in ("rf", "nn", "xgb")},
                "rf_acc": r(acc.get("rf", np.nan) * 100, 1),
                "market_home": r((lined["market_margin"] > 0).mean() * 100, 1) if len(lined) else None,
                "home_won": r(games["home_won"].mean() * 100, 1),
            })
        return out

    def season_summary(season):
        s = df[df["season"] == season]
        games = s.drop_duplicates("game_id")
        lined = games[games["market_margin"].notna() & (games["market_margin"] != 0)]
        share = s.groupby("model_type")["home_pick"].mean()
        acc = s.groupby("model_type")["is_correct"].mean()
        return {"season": f"20{season}-{int(season) + 1}", "games": len(games),
                **{k: r(share.get(k, np.nan) * 100, 1) for k in ("rf", "nn", "xgb")},
                **{f"{k}_acc": r(acc.get(k, np.nan) * 100, 1) for k in ("rf", "nn", "xgb")},
                "market_home": r((lined["market_margin"] > 0).mean() * 100, 1),
                "home_won": r(games["home_won"].mean() * 100, 1)}

    seasons = sorted(df["season"].unique())
    # (3) 16-window backtest: what recalibration changes, per window.
    e21 = load("e21_backtest.json")
    backtest = []
    for m in ("RF", "XGB"):
        d_acc, d_ece, d_home = [], [], []
        for w in e21["windows"]:
            runs = w["models"][m]
            mean = lambda k, arm: np.mean([run[arm][k] for run in runs])
            d_acc.append((mean("acc", "iso_eval") - mean("acc", "raw")) * 100)
            d_ece.append((mean("ece", "iso_eval") - mean("ece", "raw")) * 100)
            d_home.append((mean("home_pick_share", "iso_eval") - mean("home_pick_share", "raw")) * 100)
        backtest.append({"model": m.lower(), "windows": len(d_acc),
                         **{f"{k}_{s}": r(f(v), 2) for k, v in (("acc", d_acc), ("ece", d_ece), ("home", d_home))
                            for s, f in (("mean", np.mean), ("lo", min), ("hi", max))}})
    write("calibration", {
        "source": "E13 test month; public track record; 16-window calibration backtest.",
        "e13": {"n_test": e13["n_test"], "ece_raw": r(rf["raw"]["ece"], 3), "ece_iso": r(rf["isotonic"]["ece"], 3),
                "brier_raw": r(rf["raw"]["brier"], 3), "brier_iso": r(rf["isotonic"]["brier"], 3)},
        "reliability": reliability,
        "live_season": f"20{seasons[-2]}-{int(seasons[-2]) + 1}",
        "live_months": season_month(seasons[-2]),
        "seasons": [season_summary(s) for s in seasons],
        "backtest": backtest,
        "backtest_xgb_improved": int(sum(
            np.mean([run["iso_eval"]["ece"] for run in w["models"]["XGB"]])
            < np.mean([run["raw"]["ece"] for run in w["models"]["XGB"]]) for w in e21["windows"])),
        "backtest_from": e21["windows"][0]["window"][:7],
        "backtest_to": e21["windows"][-1]["window"][:7],
    })


# --- player-baselines ------------------------------------------------------

def player_baselines():
    # P2 validation (the pre-launch gate): three walk-forward seasons, each
    # predictor scored on every player-game of the test season.
    p2 = load("p2_player_validation.json")
    folds = p2["folds"]
    season = lambda name: "20" + name[-4:-2] + "-" + name[-2:]  # F1_train2223_test2324 -> 2023-24
    stats = []
    for st in PLAYER_STATS:
        pct = lambda a, b: [(f["metrics"][a][st]["mae"] - f["metrics"][b][st]["mae"]) / f["metrics"][b][st]["mae"] * 100
                            for f in folds]
        marcel_vs_naive, model_vs_naive, model_vs_marcel = pct("marcel", "naive"), pct("xgb", "naive"), pct("xgb", "marcel")
        stats.append({
            "stat": st,
            "marcel_vs_naive": r(np.mean(marcel_vs_naive), 2),
            "model_vs_naive": r(np.mean(model_vs_naive), 2),
            "model_vs_naive_worse_folds": int(sum(x > 0 for x in model_vs_naive)),
            "model_vs_marcel": r(np.mean(model_vs_marcel), 2),
            "model_vs_marcel_lo": r(min(model_vs_marcel), 2),
            "model_vs_marcel_hi": r(max(model_vs_marcel), 2),
            # paired t-test of model vs Marcel, per season
            "sig_folds": int(sum(f["paired_tests"][st]["p"] < 0.05 and f["paired_tests"][st]["delta_mae"] < 0 for f in folds)),
            "p_max": float(f"{max(f['paired_tests'][st]['p'] for f in folds):.2g}"),
            "mae": {k: r(np.mean([f["metrics"][k][st]["mae"] for f in folds]), 3) for k in ("naive", "marcel", "xgb")},
        })
    fantasy = [{"season": season(f["name"]), "n": f["n_test"],
                **{k: r(f["fantasy"][k]["fp_mae"], 2) for k in ("naive", "marcel", "xgb")}} for f in folds]

    # P6: serving Marcel's steals number instead of the model's (3 folds x 3 seeds).
    p6 = load("p6_stl_marcel.json")
    p6_runs = [{"season": season(run["fold"]), "seed": run["seed"],
                "delta": r(run["arms"]["mstl"]["vs_baseline"]["STL"]["delta_mae"], 4),
                "p": float(f"{run['arms']['mstl']['vs_baseline']['STL']['p']:.2g}")} for run in p6["runs"]]
    write("player-baselines", {
        "source": "Player-projection validation before launch: three walk-forward test seasons.",
        "n_rows": sum(f["n_test"] for f in folds),
        "seasons": [season(f["name"]) for f in folds],
        "stats": stats,
        "fantasy": fantasy,
        "p6": p6_runs,
    })


BUILDERS = {
    "signal-or-noise": signal_or_noise,
    "margin-floor": margin_floor,
    "impact-ratings": impact_ratings,
    "playoff-predictability": playoff_predictability,
    "early-season": early_season,
    "calibration": calibration,
    "player-baselines": player_baselines,
}

if __name__ == "__main__":
    for slug in sys.argv[1:] or BUILDERS:
        BUILDERS[slug]()
