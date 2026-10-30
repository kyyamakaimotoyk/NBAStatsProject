import data from "@/data/articles/calibration.json";
import Figure from "./Figure";
import { Lines, RangeChart } from "./charts";
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

export function ReliabilityFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.reliability.map((b) => ({ x: b.pred, obs: b.obs, perfect: b.pred }));
  const hi = data.reliability.find((b) => b.pred > 70 && b.pred < 80)!;
  const t =
    lang === "en"
      ? {
          title: "Random forest, one test month: how often the home team won, by the win probability the model gave",
          caption: `Points above the diagonal mean the home team won more often than the model said. Games it gave about ${Math.round(hi.pred)}% were won ${Math.round(hi.obs)}% of the time. The real outcomes were more lopsided than its probabilities: the model was timid. Each point is a 10-point band of probabilities with 10 to 47 games, so single points are rough.`,
          obs: "Random forest (raw)",
          perfect: "Perfectly calibrated",
          head: ["Model's average probability", "Home team actually won", "Games"],
          x: "Model's home-win probability",
          y: "Home team actually won",
          source: `HoopModel experiment: ${data.e13.n_test} games, March–April 2026, 10 seeds.`,
        }
      : {
          title: "ランダムフォレスト、1か月のテスト期間：モデルが示した勝率ごとの、ホームチームの実際の勝率",
          caption: `対角線より上の点は、モデルが示した数字よりもホームチームが多く勝ったことを表します。約${Math.round(hi.pred)}%とした試合では、実際には${Math.round(hi.obs)}%勝っていました。実際の結果はモデルの確率より一方的で、モデルの数字は控えめすぎたのです。点はそれぞれ確率10ポイント幅の帯で、試合数は10〜47試合と少ないため、1つ1つの点は大まかな目安です。`,
          obs: "ランダムフォレスト（補正なし）",
          perfect: "完全に較正された場合",
          head: ["モデルの平均勝率", "ホームチームの実際の勝率", "試合数"],
          x: "モデルが示したホームの勝率",
          y: "ホームの実際の勝率",
          source: `HoopModel の検証実験：2026年3〜4月の${data.e13.n_test}試合、シード値10通り。`,
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={t.source}
      table={{ head: t.head, rows: data.reliability.map((b) => [`${b.pred}%`, `${b.obs}%`, b.n]) }}
    >
      <Lines
        data={rows}
        unit="%"
        xUnit="%"
        xTicks={[30, 40, 50, 60, 70, 80]}
        yTicks={[0, 20, 40, 60, 80, 100]}
        xLabel={t.x}
        yLabel={t.y}
        series={[
          { key: "obs", name: t.obs, color: C.rf },
          { key: "perfect", name: t.perfect, color: C.neutral },
        ]}
      />
    </Figure>
  );
}

export function HomePicksFigure({ n, lang }: { n: number; lang: Lang }) {
  const months = data.live_months;
  const label = (m: string) => (lang === "en" ? m : MONTH_JA[m]);
  const rows = months.map((m, i) => ({ x: i, rf: m.rf, xgb: m.xgb, market: m.market_home }));
  const feb = months.find((m) => m.m === "Feb")!;
  const t =
    lang === "en"
      ? {
          title: `${data.live_season} regular season: share of games where each model picked the home team`,
          caption: `From January the random forest picked the home team in nearly every game, and in all of them in February and March, while the market favored the home team in about 6 games out of 10. In February its accuracy was ${feb.rf_acc}%: exactly the share of games the home team won (${feb.home_won}%). The market line starts in December because no lines were recorded for October and November.`,
          rf: "Random forest",
          xgb: "XGBoost",
          market: "Market favored home team",
          head: ["Month", "Games", "RF picked home", "NN picked home", "XGB picked home", "Market favored home", "Home team won", "RF accuracy"],
          y: "Share of games",
          source: "HoopModel track record (public predictions as graded each night).",
        }
      : {
          title: `${data.live_season}レギュラーシーズン：各モデルがホームチームの勝ちを予測した試合の割合`,
          caption: `1月以降、ランダムフォレストはほぼすべての試合でホームチームの勝ちを予測し、2月と3月にはすべての試合でそうしていました。その間、市場がホームチームを本命としていたのは10試合に6試合ほどです。2月の的中率は${feb.rf_acc}%で、その月にホームチームが勝った割合（${feb.home_won}%）とぴったり同じでした。10月・11月は最終予想点差の記録がないため、市場の線は12月から始まります。`,
          rf: "ランダムフォレスト",
          xgb: "XGBoost",
          market: "市場がホームを本命とした割合",
          head: ["月", "試合数", "RFがホームを予測", "NNがホームを予測", "XGBがホームを予測", "市場がホームを本命", "ホームの勝率", "RFの的中率"],
          y: "試合の割合",
          source: "HoopModel の予測モデルの実績（毎晩採点された公開済みの予測）。",
        };
  const pct = (v: number | null) => (v === null ? "–" : `${v}%`);
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={t.source}
      table={{
        head: t.head,
        rows: months.map((m) => [
          label(m.m),
          m.games,
          pct(m.rf),
          pct(m.nn),
          pct(m.xgb),
          pct(m.market_home),
          pct(m.home_won),
          pct(m.rf_acc),
        ]),
      }}
    >
      <Lines
        data={rows as unknown as Record<string, number>[]}
        unit="%"
        xLabels={months.map((m) => label(m.m))}
        yTicks={[0, 20, 40, 60, 80, 100]}
        yLabel={t.y}
        series={[
          { key: "rf", name: t.rf, color: C.rf },
          { key: "xgb", name: t.xgb, color: C.xgb },
          { key: "market", name: t.market, color: C.market },
        ]}
      />
    </Figure>
  );
}

export function BacktestFigure({ n, lang }: { n: number; lang: Lang }) {
  const name = (m: string) => (m === "rf" ? (lang === "en" ? "Random forest" : "ランダムフォレスト") : "XGBoost");
  const color = (m: string) => (m === "rf" ? C.rf : C.xgb);
  const acc = data.backtest.map((b) => ({ label: name(b.model), mean: b.acc_mean, lo: b.acc_lo, hi: b.acc_hi, color: color(b.model) }));
  const ece = data.backtest.map((b) => ({ label: name(b.model), mean: b.ece_mean, lo: b.ece_lo, hi: b.ece_hi, color: color(b.model) }));
  const [rf, xgb] = data.backtest;
  const t =
    lang === "en"
      ? {
          title: `What recalibration changed, across ${rf.windows} monthly test windows`,
          acc: "Change in winner accuracy (points)",
          ece: "Change in calibration error (× 100; left = better)",
          caption: `Dots are the average over ${rf.windows} windows (${data.backtest_from} to ${data.backtest_to}); lines run from the best window to the worst. Accuracy didn't improve for either model. Calibration error improved for XGBoost in ${data.backtest_xgb_improved} of ${rf.windows} windows (never worse), but not for the random forest on average. In single windows, recalibration also moved the share of home picks by up to ${Math.round(Math.abs(rf.home_lo))} points (random forest) and ${Math.round(Math.abs(xgb.home_lo))} (XGBoost).`,
          head: ["Model", "Δ accuracy (avg)", "Δ accuracy (range)", "Δ calibration error (avg)", "Δ calibration error (range)", "Δ home-pick share (range)"],
          source: "HoopModel calibration backtest: 16 monthly windows, three seeds each.",
        }
      : {
          title: `再較正で何が変わったか：${rf.windows}か月分のテスト期間で検証`,
          acc: "勝敗的中率の変化（ポイント）",
          ece: "較正誤差の変化（×100、左ほど改善）",
          caption: `点は${rf.windows}期間（${data.backtest_from}〜${data.backtest_to}）の平均、線は最も良かった期間から最も悪かった期間までの範囲です。的中率はどちらのモデルでも上がりませんでした。較正誤差は、XGBoostでは${rf.windows}期間中${data.backtest_xgb_improved}期間で改善し（悪化はなし）、ランダムフォレストでは平均すると改善していません。また、期間によっては、再較正だけでホームの勝ちを予測する割合が最大${Math.round(Math.abs(rf.home_lo))}ポイント（ランダムフォレスト）、${Math.round(Math.abs(xgb.home_lo))}ポイント（XGBoost）も動きました。`,
          head: ["モデル", "的中率の変化（平均）", "的中率の変化（範囲）", "較正誤差の変化（平均）", "較正誤差の変化（範囲）", "ホーム予測の割合の変化（範囲）"],
          source: "HoopModel の較正バックテスト：16の月別期間、各3シード。",
        };
  const range = (lo: number, hi: number) => `${lo.toFixed(1)} – ${hi.toFixed(1)}`;
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={t.source}
      table={{
        head: t.head,
        rows: data.backtest.map((b) => [
          name(b.model),
          b.acc_mean.toFixed(2),
          range(b.acc_lo, b.acc_hi),
          b.ece_mean.toFixed(2),
          range(b.ece_lo, b.ece_hi),
          range(b.home_lo, b.home_hi),
        ]),
      }}
    >
      <div className="article-figure-multiples article-figure-multiples-2">
        <div>
          <p className="article-figure-panel">{t.acc}</p>
          <RangeChart rows={acc} decimals={1} refLine={0} domain={[-6, 6]} ticks={[-6, -3, 0, 3, 6]} labelWidth={lang === "en" ? 100 : 120} />
        </div>
        <div>
          <p className="article-figure-panel">{t.ece}</p>
          <RangeChart rows={ece} decimals={1} refLine={0} domain={[-12, 12]} ticks={[-12, -6, 0, 6, 12]} labelWidth={lang === "en" ? 100 : 120} />
        </div>
      </div>
    </Figure>
  );
}
