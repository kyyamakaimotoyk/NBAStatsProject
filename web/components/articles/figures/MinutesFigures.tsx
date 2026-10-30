import data from "@/data/articles/minutes-and-misses.json";
import Figure from "./Figure";
import { Bars, Lines, RangeChart } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const STAT_LABEL: Record<string, string> = { FG3M: "3PM", FG3A: "3PA" };
const stat = (s: string) => STAT_LABEL[s] ?? s;
const seasons = data.seasons.join(", ");
const SOURCE = {
  en: `HoopModel player-projection validation before launch: ${data.n_rows.toLocaleString("en")} player-games over three test seasons (${seasons}).`,
  ja: `HoopModel の選手の成績予測の公開前検証：3つのテストシーズン（${seasons}）の${data.n_rows.toLocaleString("ja")}試合分（選手×試合）。`,
};

export function MinutesShareFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.decomp.map((d) => ({ label: stat(d.stat), share: d.share }));
  const pts = data.decomp.find((d) => d.stat === "PTS")!;
  const t =
    lang === "en"
      ? {
          title: "How much of each stat's miss disappears if the model knows the minutes actually played",
          caption: `We re-scored every projection after swapping in the minutes the player really played. For points, the average miss fell from ${pts.mae} to ${pts.mae_actual_min}: ${pts.share}%, about a sixth. For steals, blocks and turnovers, knowing the minutes barely helps. Averages over three seasons; the season-to-season range is in the table.`,
          head: ["Stat", "Miss (projected minutes)", "Miss (actual minutes)", "Share removed", "Range by season"],
          x: "Share of the average miss removed",
          name: "Share removed",
        }
      : {
          title: "実際の出場時間がわかっていたら、各スタッツの誤差はどれだけ消えるか",
          caption: `すべての予測について、出場時間だけを実際の値に差し替えて採点し直しました。得点では平均誤差が${pts.mae}から${pts.mae_actual_min}に下がり、消えたのは${pts.share}%、およそ6分の1です。スティール、ブロック、ターンオーバーでは、出場時間がわかってもほとんど変わりません。数字は3シーズンの平均で、シーズンごとの範囲は表にあります。`,
          head: ["スタッツ", "誤差（予想出場時間）", "誤差（実際の出場時間）", "消えた割合", "シーズン別の範囲"],
          x: "平均誤差のうち消えた割合",
          name: "消えた割合",
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
        rows: data.decomp.map((d) => [stat(d.stat), d.mae, d.mae_actual_min, `${d.share}%`, `${d.lo}–${d.hi}%`]),
      }}
    >
      <Bars
        data={rows}
        horizontal
        unit="%"
        decimals={1}
        domain={[0, 20]}
        valueTicks={[0, 5, 10, 15, 20]}
        labelWidth={52}
        height={rows.length * 32 + 60}
        xLabel={t.x}
        series={[{ key: "share", name: t.name, color: C.accent }]}
      />
    </Figure>
  );
}

export function PointsDecileFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.deciles.map((d) => ({ x: d.pred, actual: d.actual, perfect: d.pred }));
  const worst = Math.max(...data.deciles.map((d) => Math.abs(d.pred - d.actual)));
  const t =
    lang === "en"
      ? {
          title: "Points: projected vs actual average, from the lowest projections to the highest",
          caption: `Every player-game was sorted by its points projection and split into ten equal groups. In every group, the average actual score is within ${worst.toFixed(1)} points of the average projection: the model doesn't shave stars or inflate role players.`,
          actual: "Actual average",
          perfect: "Projection (perfect agreement)",
          head: ["Group", "Average projection", "Average actual"],
          x: "Average projected points",
          y: "Average actual points",
        }
      : {
          title: "得点：予測の低い選手から高い選手まで、予測と実際の平均の比較",
          caption: `すべての予測を得点の予測値の順に並べ、同じ数ずつ10のグループに分けました。どのグループでも、実際の得点の平均は予測の平均から${worst.toFixed(1)}点以内に収まっています。スター選手を低く見積もることも、控え選手を高く見積もることもありません。`,
          actual: "実際の平均",
          perfect: "予測（完全に一致した場合）",
          head: ["グループ", "予測の平均", "実際の平均"],
          x: "予測した得点の平均",
          y: "実際の得点の平均",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{ head: t.head, rows: data.deciles.map((d) => [d.decile, d.pred, d.actual]) }}
    >
      <Lines
        data={rows}
        xTicks={[5, 10, 15, 20, 25]}
        yDomain={[0, 30]}
        yTicks={[0, 5, 10, 15, 20, 25, 30]}
        xLabel={t.x}
        yLabel={t.y}
        series={[
          // reference first so the data line draws on top of it
          { key: "perfect", name: t.perfect, color: C.neutral },
          { key: "actual", name: t.actual, color: C.accent },
        ]}
      />
    </Figure>
  );
}

export function RangeCoverageFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.ranges.map((r) => ({
    label: stat(r.stat),
    mean: r.cov90,
    lo: r.cov90_lo,
    hi: r.cov90_hi,
    color: C.accent,
  }));
  const pts = data.ranges.find((r) => r.stat === "PTS")!;
  const t =
    lang === "en"
      ? {
          title: "90% ranges: how often the actual result landed inside, by stat",
          caption: `Each projection gets a range meant to contain the real result 9 times in 10. For points, that range is about ±${pts.half90}. Across all eleven stats and three seasons, the ranges held between ${Math.min(...data.ranges.map((r) => r.cov90_lo))}% and ${Math.max(...data.ranges.map((r) => r.cov90_hi))}% of the time, close to the 90% they promise (dashed line). Dots are three-season averages; lines span the seasons.`,
          head: ["Stat", "90% range (±)", "Held (avg)", "Held (by season)", "80% range (±)", "80% held"],
          x: "Share of games inside the 90% range",
          source: "Split-conformal ranges built from each season's held-back training games.",
        }
      : {
          title: "90%の予測幅：実際の結果が幅の中に入った割合（スタッツ別）",
          caption: `各予測には、実際の結果を10回に9回含むように作った幅があります。得点の場合、その幅は約±${pts.half90}点です。11スタッツ・3シーズンのすべてで、実際の結果が幅に入った割合は${Math.min(...data.ranges.map((r) => r.cov90_lo))}%から${Math.max(...data.ranges.map((r) => r.cov90_hi))}%で、約束どおりの90%（破線）に近い値でした。点は3シーズンの平均、線はシーズンごとの範囲です。`,
          head: ["スタッツ", "90%の幅（±）", "幅に入った割合（平均）", "シーズン別", "80%の幅（±）", "80%の幅に入った割合"],
          x: "90%の幅に入った試合の割合",
          source: "各シーズンの学習データから取り分けた試合で作った分割コンフォーマル予測の幅。",
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
        rows: data.ranges.map((r) => [
          stat(r.stat),
          r.half90,
          `${r.cov90}%`,
          `${r.cov90_lo}–${r.cov90_hi}%`,
          r.half80,
          `${r.cov80}%`,
        ]),
      }}
    >
      <RangeChart rows={rows} unit="%" decimals={1} refLine={90} domain={[85, 95]} ticks={[85, 87.5, 90, 92.5, 95]} xLabel={t.x} labelWidth={52} />
    </Figure>
  );
}
