import data from "@/data/articles/margin-floor.json";
import Figure from "./Figure";
import { Bars, Lines } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const SOURCE = {
  en: `HoopModel track record: ${data.n_games.toLocaleString("en")} graded games, ${data.from} to ${data.to}. Market: the closing line where one was recorded.`,
  ja: `HoopModel の予測モデルの実績：採点済み${data.n_games.toLocaleString("ja")}試合（${data.from}〜${data.to}）。市場：記録が残っている試合の最終予想点差。`,
};

const signed = (x: number) => (x > 0 ? `+${x}` : `${x}`);

export function MarginHistogramFigure({ n, lang }: { n: number; lang: Lang }) {
  const t =
    lang === "en"
      ? {
          title: "Final margins, home score minus away score",
          caption: `One bar per point of margin; games decided by 40 or more are stacked on the end bars. The spread is wide: standard deviation ${data.margin_sd} points, a typical game decided by ${data.margin_median_abs}, and about ${Math.round(data.share_20plus)}% of games decided by 20 or more. The gap in the middle is because NBA games can't end tied.`,
          head: ["Home margin", "Share of games", "Games"],
          x: "Home margin (points)",
          y: "Share of games",
          name: "Share of games",
        }
      : {
          title: "最終点差（ホームの得点 − アウェイの得点）",
          caption: `棒1本が1点分で、40点差以上の試合は両端の棒にまとめています。ばらつきは大きく、標準偏差は${data.margin_sd}点、典型的な試合は${data.margin_median_abs}点差で決着し、約${Math.round(data.share_20plus)}%の試合は20点差以上になります。真ん中が空いているのは、NBAの試合が引き分けで終わらないためです。`,
          head: ["ホームから見た点差", "試合の割合", "試合数"],
          x: "ホームから見た点差",
          y: "試合の割合",
          name: "試合の割合",
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
        rows: data.hist.map((h) => [
          Math.abs(h.x) === 40 ? (h.x > 0 ? "≥ +40" : "≤ −40") : signed(h.x),
          `${h.pct}%`,
          h.n,
        ]),
      }}
    >
      <Bars
        data={data.hist}
        categoryKey="x"
        unit="%"
        valueLabels={false}
        xLabel={t.x}
        yLabel={t.y}
        decimals={2}
        categoryTicks={[-40, -30, -20, -10, 0, 10, 20, 30, 40]}
        series={[{ key: "pct", name: t.name, color: C.accent }]}
      />
    </Figure>
  );
}

export function MissByPredictorFigure({ n, lang }: { n: number; lang: Lang }) {
  const names =
    lang === "en"
      ? { naive: "Always “home by 2”", rf: "Random Forest", nn: "Neural Net", xgb: "XGBoost", market: "Market closing line" }
      : { naive: "毎回「ホームが2点差」", rf: "ランダムフォレスト", nn: "ニューラルネット", xgb: "XGBoost", market: "市場の最終予想点差" };
  const color: Record<string, string> = { naive: C.neutral, rf: C.rf, nn: C.nn, xgb: C.xgb, market: C.market };
  const rows = data.miss.map((m) => ({
    label: names[m.key as keyof typeof names],
    mae: m.mae,
    color: color[m.key],
  }));
  const t =
    lang === "en"
      ? {
          title: "Average miss on the final margin, same games for every predictor",
          caption: `Scored on the ${data.n_lined.toLocaleString("en")} games with a recorded closing line. Knowing nothing gets you to about ${data.miss[0].mae.toFixed(1)}; everything the models learn about the two teams trims about one point off that, and the market trims about one more.`,
          head: ["Predictor", "Average miss (points)", "Games"],
          x: "Average miss (points)",
          name: "Average miss",
        }
      : {
          title: "最終点差の平均誤差（すべての予測を同じ試合で比較）",
          caption: `最終予想点差の記録がある${data.n_lined.toLocaleString("ja")}試合で採点しています。何も知らなくても誤差は約${data.miss[0].mae.toFixed(1)}点です。モデルが両チームについて学んだことで約1点、市場はさらに約1点縮めています。`,
          head: ["予測", "平均誤差（点）", "試合数"],
          x: "平均誤差（点）",
          name: "平均誤差",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{ head: t.head, rows: data.miss.map((m, i) => [rows[i].label, m.mae.toFixed(2), m.n]) }}
    >
      <Bars
        data={rows}
        horizontal
        decimals={1}
        domain={[0, 14]}
        colorKey="color"
        labelWidth={lang === "en" ? 125 : 135}
        height={rows.length * 42 + 50}
        xLabel={t.x}
        series={[{ key: "mae", name: t.name, color: C.neutral }]}
      />
    </Figure>
  );
}

export function WithinCurveFigure({ n, lang }: { n: number; lang: Lang }) {
  const at5 = data.within.find((w) => w.x === 5);
  const t =
    lang === "en"
      ? {
          title: "Share of games that finish within X points of the prediction",
          caption: `Read across at 5 points: only ${at5?.market}% of games land that close to the market's closing line, and ${at5?.models}% to our models. Half of the models' predictions miss by more than ${data.model_p50} points, and one in five by more than ${data.model_p80}.`,
          head: ["Within (points)", "Market", "Our models"],
          market: "Market closing line",
          models: "Our models (all three)",
          x: "Points from the prediction",
          y: "Share of games",
        }
      : {
          title: "予測から X 点以内で決着した試合の割合",
          caption: `5点のところを見ると、市場の最終予想点差から5点以内で決着した試合は${at5?.market}%、当サイトのモデルでは${at5?.models}%にとどまります。モデルの予測の半分は${data.model_p50}点以上、5試合に1試合は${data.model_p80}点以上外れています。`,
          head: ["誤差（点以内）", "市場", "当サイトのモデル"],
          market: "市場の最終予想点差",
          models: "当サイトのモデル（3つ全体）",
          x: "予測からの誤差（点）",
          y: "試合の割合",
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
        rows: data.within.filter((w) => w.x % 5 === 0).map((w) => [w.x, `${w.market}%`, `${w.models}%`]),
      }}
    >
      <Lines
        data={data.within}
        unit="%"
        refX={5}
        xTicks={[0, 5, 10, 15, 20, 25, 30]}
        xLabel={t.x}
        yLabel={t.y}
        series={[
          { key: "market", name: t.market, color: C.market },
          { key: "models", name: t.models, color: C.accent },
        ]}
      />
    </Figure>
  );
}
