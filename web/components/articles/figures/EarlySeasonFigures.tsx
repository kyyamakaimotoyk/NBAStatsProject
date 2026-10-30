import data from "@/data/articles/early-season.json";
import Figure from "./Figure";
import { Bars, Lines, RangeChart } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const MONTH_JA: Record<string, string> = {
  Oct: "10月",
  Nov: "11月",
  Dec: "12月",
  Jan: "1月",
  Feb: "2月",
  Mar: "3月",
  Apr: "4月",
};
const month = (m: string, lang: Lang) => (lang === "en" ? m : MONTH_JA[m]);
const seasons = data.seasons.join(", ");

const SOURCE = {
  en: `HoopModel track record: ${data.n_games.toLocaleString("en")} regular-season games with a closing line, seasons ${seasons}. No lines were recorded for October and November 2025, so October covers two seasons.`,
  ja: `HoopModel の予測モデルの実績：最終予想点差の記録があるレギュラーシーズンの${data.n_games.toLocaleString("ja")}試合（${seasons}シーズン）。2025年10月・11月は最終予想点差の記録がないため、10月は2シーズン分です。`,
};

export function MonthlyAccuracyFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.months.map((m, i) => ({ x: i, models: m.models, market: m.market }));
  const oct = data.months[0];
  const apr = data.months[data.months.length - 1];
  const t =
    lang === "en"
      ? {
          title: "Winner accuracy by month: our models and the betting market",
          caption: `Both climb through the season, from ${oct.models}% (models) and ${oct.market}% (market) in October to ${apr.models}% and ${apr.market}% in April. The models trail the market every month. Monthly samples are small (${oct.games} games in October, up to ${Math.max(...data.months.map((m) => m.games))} in a full month), so month-to-month wiggles of a few points are noise.`,
          models: "Our models (average of three)",
          market: "Market closing line",
          head: ["Month", "Games", "Our models", "Market", "RF", "NN", "XGB"],
          y: "Winner accuracy",
        }
      : {
          title: "月別の勝敗的中率：当サイトのモデルと賭け市場",
          caption: `どちらもシーズンが進むにつれて上がり、10月のモデル${oct.models}%・市場${oct.market}%から、4月には${apr.models}%・${apr.market}%になります。モデルはどの月も市場を下回っています。月ごとの試合数は少なく（10月は${oct.games}試合、多い月でも${Math.max(...data.months.map((m) => m.games))}試合）、数ポイント程度の上下はノイズです。`,
          models: "当サイトのモデル（3つの平均）",
          market: "市場の最終予想点差",
          head: ["月", "試合数", "当サイトのモデル", "市場", "RF", "NN", "XGB"],
          y: "勝敗的中率",
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
        rows: data.months.map((m) => [
          month(m.m, lang),
          m.games,
          `${m.models}%`,
          `${m.market}%`,
          `${m.rf}%`,
          `${m.nn}%`,
          `${m.xgb}%`,
        ]),
      }}
    >
      <Lines
        data={rows}
        unit="%"
        yDomain={[50, 80]}
        yTicks={[50, 55, 60, 65, 70, 75, 80]}
        xLabels={data.months.map((m) => month(m.m, lang))}
        yLabel={t.y}
        series={[
          { key: "models", name: t.models, color: C.accent },
          { key: "market", name: t.market, color: C.market },
        ]}
      />
    </Figure>
  );
}

export function SpreadByMonthFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.months.map((m) => ({ label: month(m.m, lang), spread: m.spread }));
  const oct = data.months[0];
  const apr = data.months[data.months.length - 1];
  const t =
    lang === "en"
      ? {
          title: "How lopsided the market expects games to be: average closing spread by month",
          caption: `The average spread grows every month, from ${oct.spread} points in October to ${apr.spread} in April. In October only ${Math.round(oct.spread8)}% of games have a favorite by 8 or more; in April, ${Math.round(apr.spread8)}%. Bigger favorites win more often, so every predictor's hit rate rises.`,
          head: ["Month", "Games", "Average spread (pts)", "Spread of 8+ points"],
          y: "Average spread (points)",
          name: "Average closing spread",
        }
      : {
          title: "市場が見込む実力差：月別の最終予想点差の平均",
          caption: `予想点差の平均は月を追うごとに広がり、10月の${oct.spread}点から4月には${apr.spread}点になります。8点差以上の本命がいる試合は、10月には${Math.round(oct.spread8)}%しかありませんが、4月には${Math.round(apr.spread8)}%です。本命の差が大きいほど本命が勝ちやすいため、どんな予測でも的中率が上がります。`,
          head: ["月", "試合数", "予想点差の平均（点）", "8点差以上の割合"],
          y: "予想点差の平均（点）",
          name: "最終予想点差の平均",
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
        rows: data.months.map((m) => [month(m.m, lang), m.games, m.spread, `${m.spread8}%`]),
      }}
    >
      <Bars
        data={rows}
        decimals={1}
        domain={[0, 10]}
        valueTicks={[0, 2, 4, 6, 8, 10]}
        yLabel={t.y}
        series={[{ key: "spread", name: t.name, color: C.market }]}
      />
    </Figure>
  );
}

export function HistoryCurveFigure({ n, lang }: { n: number; lang: Lang }) {
  const labels =
    lang === "en"
      ? ["Half a season", "1 season", "2 seasons", "3 seasons", "All since 2022"]
      : ["半シーズン", "1シーズン", "2シーズン", "3シーズン", "2022年以降すべて"];
  const rows = data.curve.map((c) => ({
    label: `${labels[c.step]} · ${c.model.toUpperCase()}`,
    mean: c.acc,
    lo: c.lo,
    hi: c.hi,
    color: c.model === "rf" ? C.rf : C.xgb,
  }));
  const first = data.curve[0].n_train;
  const last = data.curve[data.curve.length - 1].n_train;
  const t =
    lang === "en"
      ? {
          title: "Would more old data help? Accuracy on one test month by length of training history",
          caption: `Every version was scored on the same ${data.curve_n_test} games from March–April 2026. Training history ranged from half a season (${first.toLocaleString("en")} games) to everything since January 2022 (${last.toLocaleString("en")}). Dots are the average over five seeds; lines are the 95% range for a ${data.curve_n_test}-game test. All the ranges overlap: extra old seasons made no reliable difference.`,
          head: ["Training history", "Model", "Training games", "Accuracy", "95% range"],
          x: "Winner accuracy",
          source: "HoopModel experiment: fixed test month, five seeds per training length.",
        }
      : {
          title: "古いデータを増やせば良くなるか：学習に使う期間の長さと、同じテスト期間での的中率",
          caption: `すべて2026年3〜4月の同じ${data.curve_n_test}試合で採点しました。学習に使った期間は、半シーズン（${first.toLocaleString("ja")}試合）から2022年1月以降すべて（${last.toLocaleString("ja")}試合）まで。点はシード値5通りの平均、線は${data.curve_n_test}試合のテストで生じる95%の範囲です。どの範囲も重なっており、古いシーズンを足してもはっきりした差は出ませんでした。`,
          head: ["学習期間", "モデル", "学習試合数", "的中率", "95%の範囲"],
          x: "勝敗的中率",
          source: "HoopModel の検証実験：テスト期間を固定し、学習期間ごとにシード値5通り。",
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
        rows: data.curve.map((c) => [
          labels[c.step],
          c.model.toUpperCase(),
          c.n_train.toLocaleString(lang),
          `${c.acc}%`,
          `${c.lo}–${c.hi}%`,
        ]),
      }}
    >
      <RangeChart rows={rows} unit="%" domain={[60, 90]} ticks={[60, 65, 70, 75, 80, 85, 90]} xLabel={t.x} labelWidth={lang === "en" ? 150 : 140} />
    </Figure>
  );
}
