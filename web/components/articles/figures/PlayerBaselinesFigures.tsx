import data from "@/data/articles/player-baselines.json";
import Figure from "./Figure";
import { Bars, RangeChart } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const STAT_LABEL: Record<string, string> = { FG3M: "3PM", FG3A: "3PA" };
const stat = (s: string) => STAT_LABEL[s] ?? s;
const seasons = data.seasons.join(", ");

const SOURCE = {
  en: `HoopModel player-projection validation before launch: ${data.n_rows.toLocaleString("en")} player-games over three test seasons (${seasons}), each predicted by a model trained only on earlier seasons.`,
  ja: `HoopModel の選手の成績予測の公開前検証：3つのテストシーズン（${seasons}）の${data.n_rows.toLocaleString("ja")}試合分（選手×試合）。各シーズンは、それより前のシーズンだけで学習したモデルで予測。`,
};

const NAMES = {
  en: { naive: "10-game average", marcel: "Marcel", model: "Our model" },
  ja: { naive: "直近10試合の平均", marcel: "Marcel", model: "当サイトのモデル" },
};

export function VsNaiveFigure({ n, lang }: { n: number; lang: Lang }) {
  const names = NAMES[lang];
  const rows = data.stats.map((s) => ({ label: stat(s.stat), marcel: s.marcel_vs_naive, model: s.model_vs_naive }));
  const better = data.stats.filter((s) => s.marcel_vs_naive < 0).map((s) => stat(s.stat));
  const fg3a = data.stats.find((s) => s.stat === "FG3A")!;
  const t =
    lang === "en"
      ? {
          title: "Change in average error compared with a plain 10-game average, by stat",
          caption: `Left of zero means smaller errors than the 10-game average. Marcel beat it only on ${better.join(", ")}, and was worse on the other eight, most of all on 3-point attempts (${fg3a.marcel_vs_naive > 0 ? "+" : ""}${fg3a.marcel_vs_naive.toFixed(1)}%). Our model beat it on everything except blocks, where the two are effectively tied. Averages over three seasons.`,
          head: ["Stat", "10-game avg error", "Marcel error", "Model error", "Marcel vs 10-game", "Model vs 10-game"],
          x: "Change in average error vs the 10-game average",
        }
      : {
          title: "直近10試合の平均と比べた平均誤差の変化（スタッツ別）",
          caption: `0より左は、直近10試合の平均よりも誤差が小さいことを表します。Marcelがこれを上回ったのは${better.join("・")}だけで、残りの8つでは下回り、特に3ポイント試投数では大きく悪化しました（${fg3a.marcel_vs_naive > 0 ? "+" : ""}${fg3a.marcel_vs_naive.toFixed(1)}%）。当サイトのモデルは、事実上引き分けのBLKを除くすべてで上回りました。数字は3シーズンの平均です。`,
          head: ["スタッツ", "直近10試合平均の誤差", "Marcelの誤差", "モデルの誤差", "Marcel（対10試合平均）", "モデル（対10試合平均）"],
          x: "直近10試合の平均と比べた平均誤差の変化",
        };
  const pct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{
        head: t.head,
        rows: data.stats.map((s) => [
          stat(s.stat),
          s.mae.naive.toFixed(3),
          s.mae.marcel.toFixed(3),
          s.mae.xgb.toFixed(3),
          pct(s.marcel_vs_naive),
          pct(s.model_vs_naive),
        ]),
      }}
    >
      <Bars
        data={rows}
        horizontal
        unit="%"
        decimals={1}
        domain={[-10, 6]}
        valueTicks={[-10, -8, -6, -4, -2, 0, 2, 4, 6]}
        refLine={0}
        valueLabels={false}
        labelWidth={52}
        height={rows.length * 40 + 80}
        xLabel={t.x}
        series={[
          { key: "marcel", name: names.marcel, color: C.neutral },
          { key: "model", name: names.model, color: C.accent },
        ]}
      />
    </Figure>
  );
}

export function VsMarcelFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.stats.map((s) => ({
    label: stat(s.stat),
    mean: s.model_vs_marcel,
    lo: s.model_vs_marcel_lo,
    hi: s.model_vs_marcel_hi,
    color: s.sig_folds === data.seasons.length ? C.accent : C.neutral,
  }));
  const wins = data.stats.filter((s) => s.sig_folds === data.seasons.length).length;
  const t =
    lang === "en"
      ? {
          title: "Our model against Marcel: change in average error, by stat",
          caption: `Dots are the average over three seasons; lines run from the best season to the worst. Orange stats were significantly better than Marcel in every season (paired tests on the same player-games); that's ${wins} of 11. Steals, in gray, crossed zero: the model and Marcel are effectively tied there.`,
          head: ["Stat", "Avg change", "Best season", "Worst season", "Seasons significantly better", "Largest p-value"],
          x: "Change in average error vs Marcel",
        }
      : {
          title: "当サイトのモデルとMarcelの比較：平均誤差の変化（スタッツ別）",
          caption: `点は3シーズンの平均、線は最も良かったシーズンから最も悪かったシーズンまでの範囲です。オレンジは、すべてのシーズンでMarcelより有意に良かったスタッツ（同じ選手・試合での対応のある検定）で、11のうち${wins}つです。灰色のSTLは0をまたいでおり、モデルとMarcelは事実上引き分けです。`,
          head: ["スタッツ", "平均の変化", "最良のシーズン", "最悪のシーズン", "有意に良かったシーズン数", "最大のp値"],
          x: "Marcelと比べた平均誤差の変化",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{
        head: t.head,
        rows: data.stats.map((s) => [
          stat(s.stat),
          `${s.model_vs_marcel.toFixed(2)}%`,
          `${s.model_vs_marcel_lo.toFixed(2)}%`,
          `${s.model_vs_marcel_hi.toFixed(2)}%`,
          `${s.sig_folds} / ${data.seasons.length}`,
          s.p_max,
        ]),
      }}
    >
      <RangeChart
        rows={rows}
        unit="%"
        decimals={1}
        refLine={0}
        domain={[-10, 2]}
        ticks={[-10, -8, -6, -4, -2, 0, 2]}
        xLabel={t.x}
        labelWidth={52}
      />
    </Figure>
  );
}

export function FantasyFigure({ n, lang }: { n: number; lang: Lang }) {
  const names = NAMES[lang];
  const rows = data.fantasy.map((f) => ({ label: f.season, naive: f.naive, marcel: f.marcel, model: f.xgb }));
  const avg = (k: "naive" | "marcel" | "xgb") => data.fantasy.reduce((a, f) => a + f[k], 0) / data.fantasy.length;
  const gain = Math.round((1 - avg("xgb") / avg("naive")) * 100);
  const t =
    lang === "en"
      ? {
          title: "Fantasy points: average miss per player-game, by season",
          caption: `Our model misses by about ${avg("xgb").toFixed(1)} fantasy points per player-game, against ${avg("marcel").toFixed(1)} for Marcel and ${avg("naive").toFixed(1)} for the 10-game average: roughly ${gain}% smaller, every season. The bars are close because most of a single game's swing can't be predicted by anyone.`,
          head: ["Season", "Player-games", names.naive, names.marcel, names.model],
          y: "Average miss (fantasy pts)",
        }
      : {
          title: "ファンタジーポイント：選手1人・1試合あたりの平均誤差（シーズン別）",
          caption: `当サイトのモデルの誤差は選手1人・1試合あたり約${avg("xgb").toFixed(1)}ポイントで、Marcelの${avg("marcel").toFixed(1)}、直近10試合平均の${avg("naive").toFixed(1)}より、どのシーズンでも約${gain}%小さくなっています。棒の差が小さく見えるのは、1試合ごとの振れ幅の大部分が、誰にも予測できないものだからです。`,
          head: ["シーズン", "選手×試合数", names.naive, names.marcel, names.model],
          y: "平均誤差（ファンタジーポイント）",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{
        head: t.head,
        rows: data.fantasy.map((f) => [f.season, f.n.toLocaleString(lang), f.naive, f.marcel, f.xgb]),
      }}
    >
      <Bars
        data={rows}
        decimals={1}
        domain={[0, 10]}
        valueTicks={[0, 2, 4, 6, 8, 10]}
        yLabel={t.y}
        series={[
          { key: "naive", name: names.naive, color: C.market },
          { key: "marcel", name: names.marcel, color: C.neutral },
          { key: "model", name: names.model, color: C.accent },
        ]}
      />
    </Figure>
  );
}
