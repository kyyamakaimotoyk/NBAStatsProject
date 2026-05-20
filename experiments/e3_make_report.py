"""
Generates a markdown report from e3 ablation JSON outputs.

Takes one or two JSON paths (one per CSV variant). Emits per-CSV summary
tables (config × model × metric with bootstrap mean/CI) and pairwise
significance tables (each non-baseline config vs baseline). If two JSONs
are passed, also emits an E7-effect comparison.

Usage:
    python experiments/e3_make_report.py \
        --e7on outputs/e3_ablation_e7on.json \
        --e7off outputs/e3_ablation_e7off.json \
        --out docs/e3_ablation_report.md
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional


def fmt_pct(x: float) -> str:
    return f'{x*100:.2f}'


def fmt_mae(x: float) -> str:
    return f'{x:.3f}'


def fmt_auc(x: float) -> str:
    return f'{x:.4f}'


def fmt_p(p: float) -> str:
    if p < 0.001: return '<0.001'
    if p < 0.01:  return f'{p:.3f}**'
    if p < 0.05:  return f'{p:.3f}*'
    return f'{p:.3f}'


def sig_marker(p: float) -> str:
    if p < 0.001: return '***'
    if p < 0.01:  return '**'
    if p < 0.05:  return '*'
    return ''


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def parse_summary_key(k: str):
    cfg, model, metric = k.split('|')
    return cfg, model, metric


def parse_paired_key(k: str):
    cfg, model = k.split('|')
    return cfg, model


def render_summary_table(data: dict, title: str) -> str:
    """Per-CSV summary: config × model × metric → mean [CI_low, CI_high]."""
    configs = data['configs']
    models = data['models']
    summary = data['summary']

    lines = [f'\n### {title}']
    lines.append(f'\n*Bootstrap-CI (95%) from {len(data["seeds"])} seeds × {data["n_bootstrap"]} test-set resamples per cell. n_test={data["n_test"]}.*\n')

    for model in models:
        lines.append(f'\n**{model}**\n')
        lines.append('| Config | Accuracy (%) | AUC | MAE |')
        lines.append('|---|---|---|---|')
        for cfg in configs:
            acc = summary.get(f'{cfg}|{model}|acc', {})
            auc = summary.get(f'{cfg}|{model}|auc', {})
            mae = summary.get(f'{cfg}|{model}|mae', {})
            if not acc:
                continue
            acc_str = f'{fmt_pct(acc["mean"])} [{fmt_pct(acc["ci_lo"])}, {fmt_pct(acc["ci_hi"])}]'
            auc_str = f'{fmt_auc(auc["mean"])} [{fmt_auc(auc["ci_lo"])}, {fmt_auc(auc["ci_hi"])}]'
            mae_str = f'{fmt_mae(mae["mean"])} [{fmt_mae(mae["ci_lo"])}, {fmt_mae(mae["ci_hi"])}]'
            lines.append(f'| {cfg} | {acc_str} | {auc_str} | {mae_str} |')
    return '\n'.join(lines)


def render_paired_table(data: dict, title: str) -> str:
    """Pairwise: each non-baseline config vs baseline."""
    paired = data['paired']
    models = data['models']
    baseline = data.get('baseline_label', 'baseline')

    lines = [f'\n### {title}']
    lines.append(f'\n*All comparisons vs `{baseline}`. McNemar = paired test on classifier agreement; '
                 f'paired-t = on per-game |error| diff for MAE; bootstrap-AUC = on AUC delta.*')
    lines.append('\n*Significance: `*` p<0.05, `**` p<0.01, `***` p<0.001.*\n')

    for model in models:
        lines.append(f'\n**{model}** — config-vs-baseline\n')
        lines.append('| Config | Acc gain (cfg-wins/base-wins) | McNemar p | MAE Δ | paired-t p | AUC Δ [95% CI] | AUC p |')
        lines.append('|---|---|---|---|---|---|---|')
        for k in sorted(paired.keys()):
            cfg, m = parse_paired_key(k)
            if m != model:
                continue
            v = paired[k]
            acc_delta = (v['cfg_wins'] - v['base_wins']) / data['n_test']
            mae_d = v['mae_diff_mean']
            mae_sig = sig_marker(v['paired_t_p'])
            mc_p = fmt_p(v['mcnemar_p'])
            t_p = fmt_p(v['paired_t_p'])
            auc_d = v['auc_diff_mean']
            auc_ci = f'[{v["auc_diff_ci_lo"]:.4f}, {v["auc_diff_ci_hi"]:.4f}]'
            auc_p = fmt_p(v['auc_diff_p'])
            lines.append(
                f'| {cfg} | {fmt_pct(acc_delta)}pp ({v["cfg_wins"]}/{v["base_wins"]}) | {mc_p} '
                f'| {mae_d:+.3f}{mae_sig} | {t_p} | {auc_d:+.4f} {auc_ci} | {auc_p} |'
            )
    return '\n'.join(lines)


def render_e7_comparison(e7on: dict, e7off: dict) -> str:
    """Compare full-config (E9+E10+E11) results across E7-on vs E7-off CSVs to
    isolate E7's marginal contribution."""
    lines = ['\n### E7 effect — full-config (E9+E10+E11) results across CSVs']
    lines.append('\n*Same model config, same seeds, two CSVs differing only in '
                 'how `_AVAILABLE` columns were populated (pregame injury report = E7-on, '
                 'postgame boxscore = E7-off).*\n')

    cfgs_to_compare = ['baseline', 'E9+E10+E11_full']
    models = e7on['models']

    for cfg in cfgs_to_compare:
        for model in models:
            on_acc = e7on['summary'].get(f'{cfg}|{model}|acc', {})
            off_acc = e7off['summary'].get(f'{cfg}|{model}|acc', {})
            on_mae = e7on['summary'].get(f'{cfg}|{model}|mae', {})
            off_mae = e7off['summary'].get(f'{cfg}|{model}|mae', {})
            on_auc = e7on['summary'].get(f'{cfg}|{model}|auc', {})
            off_auc = e7off['summary'].get(f'{cfg}|{model}|auc', {})
            if not on_acc or not off_acc:
                continue
            lines.append(f'\n**{model} / {cfg}**')
            lines.append('| Metric | E7-on (pregame) | E7-off (postgame) | Δ (E7-on − E7-off) |')
            lines.append('|---|---|---|---|')
            lines.append(f'| Accuracy | {fmt_pct(on_acc["mean"])}% [{fmt_pct(on_acc["ci_lo"])}, {fmt_pct(on_acc["ci_hi"])}] '
                         f'| {fmt_pct(off_acc["mean"])}% [{fmt_pct(off_acc["ci_lo"])}, {fmt_pct(off_acc["ci_hi"])}] '
                         f'| {fmt_pct(on_acc["mean"] - off_acc["mean"])}pp |')
            lines.append(f'| AUC | {fmt_auc(on_auc["mean"])} [{fmt_auc(on_auc["ci_lo"])}, {fmt_auc(on_auc["ci_hi"])}] '
                         f'| {fmt_auc(off_auc["mean"])} [{fmt_auc(off_auc["ci_lo"])}, {fmt_auc(off_auc["ci_hi"])}] '
                         f'| {on_auc["mean"] - off_auc["mean"]:+.4f} |')
            lines.append(f'| MAE | {fmt_mae(on_mae["mean"])} [{fmt_mae(on_mae["ci_lo"])}, {fmt_mae(on_mae["ci_hi"])}] '
                         f'| {fmt_mae(off_mae["mean"])} [{fmt_mae(off_mae["ci_lo"])}, {fmt_mae(off_mae["ci_hi"])}] '
                         f'| {on_mae["mean"] - off_mae["mean"]:+.3f} |')

    return '\n'.join(lines)


def render_recommendation(e7on: dict, e7off: Optional[dict]) -> str:
    """Programmatic recommendation: which features pass significance vs baseline?"""
    lines = ['\n## Recommendation: which features to keep']
    lines.append('\n*Decision rule: keep a feature group iff at least ONE of '
                 '{RF, XGB} shows a statistically significant improvement '
                 '(p<0.05) on at least one of {accuracy via McNemar, MAE via paired-t, AUC via bootstrap}.*\n')

    paired = e7on['paired']
    candidates = ['E9_only', 'E10_only', 'E11_only']
    decisions = {}
    for cfg in candidates:
        wins = []
        for k in paired:
            ck, mk = parse_paired_key(k)
            if ck != cfg:
                continue
            v = paired[k]
            if v['mcnemar_p'] < 0.05:
                wins.append(f'{mk} accuracy (McNemar p={fmt_p(v["mcnemar_p"])})')
            if v['paired_t_p'] < 0.05 and v['mae_diff_mean'] < 0:
                wins.append(f'{mk} MAE (paired-t p={fmt_p(v["paired_t_p"])}, Δ={v["mae_diff_mean"]:.3f})')
            if v['auc_diff_p'] < 0.05 and v['auc_diff_mean'] > 0:
                wins.append(f'{mk} AUC (bootstrap p={fmt_p(v["auc_diff_p"])}, Δ={v["auc_diff_mean"]:+.4f})')
        decisions[cfg] = wins

    for cfg, wins in decisions.items():
        if wins:
            lines.append(f'\n### {cfg}: **KEEP** ({len(wins)} significant test(s))')
            for w in wins:
                lines.append(f'  - {w}')
        else:
            lines.append(f'\n### {cfg}: **CONSIDER DROPPING** (no significant improvement at p<0.05)')

    # E7 recommendation (if both CSVs provided)
    if e7off is not None:
        lines.append('\n### E7 (pre-game injury data)')
        lines.append('\n*E7 isn\'t a feature toggle; it changes the *content* of `_AVAILABLE` columns. '
                     'We compare same-config results across the two CSVs.*\n')
        # Use full-config row to evaluate
        e7_wins = []
        for model in e7on['models']:
            on_acc = e7on['summary'].get(f'E9+E10+E11_full|{model}|acc', {}).get('mean')
            off_acc = e7off['summary'].get(f'E9+E10+E11_full|{model}|acc', {}).get('mean')
            on_mae = e7on['summary'].get(f'E9+E10+E11_full|{model}|mae', {}).get('mean')
            off_mae = e7off['summary'].get(f'E9+E10+E11_full|{model}|mae', {}).get('mean')
            if None in (on_acc, off_acc, on_mae, off_mae):
                continue
            lines.append(f'  - {model}: acc Δ = {(on_acc-off_acc)*100:+.2f}pp, MAE Δ = {on_mae-off_mae:+.3f}')
            # Heuristic: keep E7 if it gives >0.5pp accuracy or >0.2 MAE reduction
            if on_acc - off_acc > 0.005 or off_mae - on_mae > 0.2:
                e7_wins.append(model)
        if e7_wins:
            lines.append(f'\n  → **KEEP E7** (helps on {e7_wins} by heuristic threshold)')
        else:
            lines.append('\n  → **CONSIDER DROPPING E7** (no clear improvement vs postgame variant)')
        lines.append('\n  *Note: this is a single-CSV-pair comparison without a paired test between CSVs '
                     '(seeds re-run on different data). Treat as directional, not formally significant.*')

    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--e7on', required=True, help='JSON for E7-on CSV ablation')
    ap.add_argument('--e7off', default=None, help='JSON for E7-off CSV ablation (optional)')
    ap.add_argument('--out', default='docs/e3_ablation_report.md')
    args = ap.parse_args()

    e7on = load(args.e7on)
    e7off = load(args.e7off) if args.e7off else None

    lines = []
    lines.append('# E3 noise-aware feature ablation — full report\n')
    lines.append(f'_Generated: {datetime.now().isoformat(timespec="seconds")}_\n')
    lines.append('\n## Method\n')
    lines.append(f'\nW5 walk-forward window: train on games strictly before 2026-03-15, test '
                 f'on 2026-03-15 → 2026-04-15 (n_test={e7on["n_test"]}, n_train={e7on["n_train"]}).')
    lines.append('\nFor each of 8 (E9, E10, E11) toggle configurations × 10 seeds × {RF, XGB}: '
                 'train fresh, predict on W5 test. Each prediction set bootstrap-resampled '
                 f'{e7on["n_bootstrap"]} times → 10 seeds × {e7on["n_bootstrap"]} = '
                 f'{10*e7on["n_bootstrap"]:,} metric measurements per cell.')
    lines.append('\nPairwise comparisons use predictions averaged across seeds; McNemar χ² for '
                 'accuracy, paired t-test on per-game |error| for MAE, bootstrap on the AUC delta.')

    # ---- E7-on tables ----
    lines.append('\n## CSV: E7-on (pregame injury report)\n')
    lines.append(render_summary_table(e7on, 'Bootstrap CIs by config × model'))
    lines.append(render_paired_table(e7on, 'Pairwise significance vs baseline'))

    # ---- E7-off tables ----
    if e7off is not None:
        lines.append('\n## CSV: E7-off (postgame boxscore)\n')
        lines.append(render_summary_table(e7off, 'Bootstrap CIs by config × model'))
        lines.append(render_paired_table(e7off, 'Pairwise significance vs baseline'))
        lines.append(render_e7_comparison(e7on, e7off))

    # ---- Recommendation ----
    lines.append(render_recommendation(e7on, e7off))

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'Report written -> {args.out}')


if __name__ == '__main__':
    main()
