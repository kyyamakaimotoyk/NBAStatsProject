import data from "@/data/articles/impact-ratings.json";
import Figure from "./Figure";
import { Bars, RangeChart } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const STAT_LABEL: Record<string, string> = { FG3M: "3PM", FG3A: "3PA" };

export function PlayerNullFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.player.map((s) => ({
    label: STAT_LABEL[s.stat] ?? s.stat,
    mean: s.pct,
    lo: s.lo,
    hi: s.hi,
    color: C.accent,
  }));
  const t =
    lang === "en"
      ? {
          title: "Player model: change in average error after adding impact ratings",
          caption:
            "Left of zero means smaller errors. Dots are the average over three test seasons and three seeds; lines run from the best run to the worst. Every stat straddles zero, and the largest average change (points) is about a tenth of a percent.",
          head: ["Stat", "Avg change in error", "Best run", "Worst run"],
          x: "Change in average error",
          source: "HoopModel player-model experiment: three test seasons (2023-24 to 2025-26), three seeds each.",
        }
      : {
          title: "選手モデル：インパクト指標を加えたときの平均誤差の変化",
          caption:
            "0より左は誤差が小さくなったことを表します。点は3つのテストシーズン×3シードの平均、線は最も良かった回から最も悪かった回までの範囲です。どのスタッツも0をまたいでおり、平均で最も大きく動いたPTSでも変化は約0.1%です。",
          head: ["スタッツ", "平均誤差の変化（平均）", "最良の回", "最悪の回"],
          x: "平均誤差の変化",
          source: "HoopModel の選手モデル検証：3つのテストシーズン（2023-24〜2025-26）、各3シード。",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={t.source}
      table={{
        head: t.head,
        rows: data.player.map((s, i) => [rows[i].label, `${s.pct.toFixed(3)}%`, `${s.lo.toFixed(3)}%`, `${s.hi.toFixed(3)}%`]),
      }}
    >
      <RangeChart rows={rows} unit="%" decimals={2} refLine={0} domain={[-0.5, 0.5]} ticks={[-0.5, -0.25, 0, 0.25, 0.5]} xLabel={t.x} labelWidth={52} />
    </Figure>
  );
}

export function StandaloneSignalFigure({ n, lang }: { n: number; lang: Lang }) {
  const labels =
    lang === "en"
      ? ["Away much better", "Away better", "About even", "Home better", "Home much better"]
      : ["アウェイが大きく上", "アウェイが上", "ほぼ互角", "ホームが上", "ホームが大きく上"];
  const rows = data.buckets.map((b, i) => ({ label: labels[i], win: b.win_pct, n: b.n }));
  const t =
    lang === "en"
      ? {
          title: "Home win rate by the two rosters' prior-season impact ratings",
          caption: `Games split into five equal groups by the gap between the two teams' minutes-weighted ratings. On its own the signal is strong: home teams win ${data.buckets[0].win_pct.toFixed(1)}% of games in the bottom group and ${data.buckets[4].win_pct}% in the top one, and the gap correlates with the final margin at r = ${data.team_corr}.`,
          head: ["Rating gap (fifth)", "Home win rate", "Games"],
          y: "Home win rate",
          name: "Home win rate",
          source: `${data.team_n.toLocaleString("en")} games, 2022–2026, with a prior-season rating for both teams.`,
        }
      : {
          title: "前シーズンのインパクト指標の差と、ホームチームの勝率",
          caption: `両チームの指標（出場時間で加重平均）の差で、試合を同じ数ずつ5つのグループに分けました。単独で見るとシグナルは強く、ホームの勝率は最も不利なグループで${data.buckets[0].win_pct.toFixed(1)}%、最も有利なグループで${data.buckets[4].win_pct}%です。指標の差と最終点差の相関係数は r = ${data.team_corr} です。`,
          head: ["指標の差（5分位）", "ホームの勝率", "試合数"],
          y: "ホームの勝率",
          name: "ホームの勝率",
          source: `2022〜2026年の${data.team_n.toLocaleString("ja")}試合（両チームに前シーズンの指標があるもの）。`,
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={t.source}
      table={{ head: t.head, rows: rows.map((r) => [r.label, `${r.win}%`, r.n]) }}
    >
      <Bars
        data={rows}
        unit="%"
        domain={[0, 100]}
        refLine={50}
        yLabel={t.y}
        series={[{ key: "win", name: t.name, color: C.accent }]}
      />
    </Figure>
  );
}

export function InModelFigure({ n, lang }: { n: number; lang: Lang }) {
  const stage =
    lang === "en"
      ? { month: "1 month", pooled: "21 months" }
      : { month: "1か月", pooled: "21か月分" };
  // AUC in hundredths so the axis reads in "points of AUC".
  const rows = data.inmodel.map((m) => ({
    label: `${stage[m.stage as keyof typeof stage]} · ${m.model.toUpperCase()}`,
    mean: m.auc * 100,
    lo: m.auc_lo * 100,
    hi: m.auc_hi * 100,
    color: m.model === "rf" ? C.rf : C.xgb,
  }));
  const t =
    lang === "en"
      ? {
          title: "Team model: change in ranking quality (AUC) after adding the ratings",
          caption:
            "Dots are the average change, lines the 95% confidence interval from paired resampling, in hundredths of AUC. Every interval includes zero, on the 230-game held-out month and on 4,032 games pooled across 21 months. Margin error didn't move either (see the table).",
          head: ["Test", "Model", "Games", "Δ AUC", "95% CI", "Δ margin error (pts)", "95% CI"],
          x: "Change in AUC (hundredths)",
          source: "HoopModel team-model experiment; RF and XGBoost, 10 seeds on the held-out month, 3 seeds per monthly window.",
        }
      : {
          title: "チームモデル：指標を加えたときの、勝率による並べ方の質（AUC）の変化",
          caption:
            "点は平均の変化、線は対応のあるリサンプリングによる95%信頼区間で、単位はAUCの0.01です。検証用の1か月（230試合）でも、21か月分をまとめた4,032試合でも、すべての区間が0を含んでいます。点差の誤差も変わりませんでした（表を参照）。",
          head: ["検証", "モデル", "試合数", "AUCの変化", "95%信頼区間", "点差誤差の変化（点）", "95%信頼区間"],
          x: "AUCの変化（0.01単位）",
          source: "HoopModel のチームモデル検証：RFとXGBoost。検証用の1か月はシード値10通り、月別期間は各3シード。",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={t.source}
      table={{
        head: t.head,
        rows: data.inmodel.map((m) => [
          stage[m.stage as keyof typeof stage],
          m.model.toUpperCase(),
          m.n.toLocaleString(lang),
          m.auc.toFixed(4),
          `${m.auc_lo.toFixed(4)} – ${m.auc_hi.toFixed(4)}`,
          m.mae.toFixed(3),
          `${m.mae_lo.toFixed(3)} – ${m.mae_hi.toFixed(3)}`,
        ]),
      }}
    >
      <RangeChart rows={rows} decimals={2} refLine={0} domain={[-1.5, 1.5]} ticks={[-1.5, -1, -0.5, 0, 0.5, 1, 1.5]} xLabel={t.x} labelWidth={lang === "en" ? 115 : 100} />
    </Figure>
  );
}
