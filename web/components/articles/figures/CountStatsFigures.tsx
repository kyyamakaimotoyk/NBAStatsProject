import data from "@/data/articles/count-stats.json";
import Figure from "./Figure";
import { Bars, RangeChart } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";
type Bin = (typeof data.bins.STL)[number];

const seasons = data.seasons.join(", ");
const SOURCE = {
  en: `HoopModel player-projection validation before launch: ${data.n_rows.toLocaleString("en")} player-games over three test seasons (${seasons}), pooled. Bins with fewer than 200 player-games are left out.`,
  ja: `HoopModel の選手の成績予測の公開前検証：3つのテストシーズン（${seasons}）の${data.n_rows.toLocaleString("ja")}試合分（選手×試合）をまとめて集計。200試合未満の帯は除外。`,
};
const STAT = {
  en: { STL: "Steals", BLK: "Blocks" },
  ja: { STL: "スティール", BLK: "ブロック" },
};
const binLabel = (b: Bin) => b.bin.replace("-", "–");
// Compact form for crowded axes: "0.5-1.0" -> ".5–1"
const shortBin = (b: Bin) =>
  b.bin
    .split("-")
    .map((v) => v.replace(/\.0$/, "").replace(/^0\./, "."))
    .join("–");

export function TypicalShapeFigure({ n, lang }: { n: number; lang: Lang }) {
  const stl = data.bins.STL.find((b) => b.bin === "0.5-1.0")!;
  const blk = data.bins.BLK.find((b) => b.bin === "0-0.5")!;
  const rows = (b: Bin) => [
    { label: "0", predicted: b.imp_p0, actual: b.emp_p0 },
    { label: "1", predicted: b.imp_p1, actual: b.emp_p1 },
    { label: "2+", predicted: b.imp_p2plus, actual: b.emp_p2plus },
  ];
  const t =
    lang === "en"
      ? {
          title: "One expected rate, three outcomes: predicted vs actual share of games",
          stl: `Steals: players expected for ${binLabel(stl)} (${stl.n.toLocaleString("en")} player-games)`,
          blk: `Blocks: players expected for ${binLabel(blk)} (${blk.n.toLocaleString("en")} player-games)`,
          predicted: "Predicted by the rate",
          actual: "Actually happened",
          caption: `For the most common kind of player, the rate gets the whole shape about right: every predicted share is within about two points of what happened. Real games have slightly fewer 1s and slightly more 0s and 2+ than the curve says, a hint of what goes wrong further out.`,
          head: ["Stat and band", "Outcome", "Predicted", "Actual"],
          outcome: (o: string) => (o === "2+" ? "2 or more" : o),
        }
      : {
          title: "1つの期待値から3つの結果へ：予測した割合と実際の割合",
          stl: `スティール：期待値${binLabel(stl)}の選手（${stl.n.toLocaleString("ja")}試合分）`,
          blk: `ブロック：期待値${binLabel(blk)}の選手（${blk.n.toLocaleString("ja")}試合分）`,
          predicted: "期待値から予測した割合",
          actual: "実際の割合",
          caption: `最も多いタイプの選手では、期待値から求めた分布が全体の形をほぼ正しく捉えていて、どの割合も実際との差は約2ポイント以内です。実際の試合では1回の試合がわずかに少なく、0回と2回以上がわずかに多くなっています。これが、さらに外側で起きるずれの兆しです。`,
          head: ["スタッツと帯", "結果", "予測", "実際"],
          outcome: (o: string) => (o === "2+" ? "2回以上" : `${o}回`),
        };
  const series = [
    { key: "predicted", name: t.predicted, color: C.neutral },
    { key: "actual", name: t.actual, color: C.accent },
  ];
  const tableRows = (label: string, b: Bin) =>
    rows(b).map((r) => [label, t.outcome(r.label), `${r.predicted}%`, `${r.actual}%`]);
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{
        head: t.head,
        rows: [
          ...tableRows(`${STAT[lang].STL} ${binLabel(stl)}`, stl),
          ...tableRows(`${STAT[lang].BLK} ${binLabel(blk)}`, blk),
        ],
      }}
    >
      <p className="article-figure-legend">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </p>
      <div className="article-figure-multiples article-figure-multiples-2">
        <div>
          <p className="article-figure-panel">{t.stl}</p>
          <Bars data={rows(stl)} series={series} legend={false} unit="%" decimals={0} domain={[0, 100]} valueTicks={[0, 25, 50, 75, 100]} height={220} />
        </div>
        <div>
          <p className="article-figure-panel">{t.blk}</p>
          <Bars data={rows(blk)} series={series} legend={false} unit="%" decimals={0} domain={[0, 100]} valueTicks={[0, 25, 50, 75, 100]} height={220} />
        </div>
      </div>
    </Figure>
  );
}

export function TailGapFigure({ n, lang }: { n: number; lang: Lang }) {
  const t =
    lang === "en"
      ? {
          title: "Where the rate slips: actual minus predicted share of games, by expected rate",
          zero: "Games with none",
          two: "Games with 2 or more",
          x: "Expected per game",
          caption: (top: Bin) =>
            `Above zero means it happened more often than the rate predicted. The higher a player's expected rate, the bigger the surplus of nights with none: for players expected to block 2–3 shots, zero-block games happened ${top.emp_p0}% of the time against ${top.imp_p0}% predicted, and 2+ games ${top.emp_p2plus}% against ${top.imp_p2plus}%. The extra zeros were positive in every season for those players.`,
          head: ["Stat", "Expected per game", "Player-games", "None: predicted", "None: actual", "2+: predicted", "2+: actual", "None gap by season"],
        }
      : {
          title: "期待値のずれ：期待値の帯ごとの、実際の割合と予測した割合の差",
          zero: "0回の試合",
          two: "2回以上の試合",
          x: "1試合あたりの期待値",
          caption: (top: Bin) =>
            `0より上は、予測より実際のほうが多かったことを表します。期待値の高い選手ほど、記録ゼロの試合が予測を上回る幅が大きくなります。ブロックの期待値が2〜3本の選手では、0本の試合が予測${top.imp_p0}%に対して実際は${top.emp_p0}%、2本以上の試合は予測${top.imp_p2plus}%に対して実際は${top.emp_p2plus}%でした。こうした選手のゼロの試合の上振れは、どのシーズンでもプラスでした。`,
          head: ["スタッツ", "1試合あたりの期待値", "試合数", "0回：予測", "0回：実際", "2回以上：予測", "2回以上：実際", "0回の差（シーズン別の範囲）"],
        };
  const series = [
    { key: "zero", name: t.zero, color: C.accent },
    { key: "two", name: t.two, color: C.neutral },
  ];
  const rows = (bins: Bin[]) => bins.map((b) => ({ label: shortBin(b), zero: b.d_p0, two: b.d_p2 }));
  const top = data.bins.BLK[data.bins.BLK.length - 1];
  const pts = lang === "en" ? " pts" : "ポイント";
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption(top)}
      source={SOURCE[lang]}
      table={{
        head: t.head,
        rows: (["STL", "BLK"] as const).flatMap((st) =>
          data.bins[st].map((b) => [
            STAT[lang][st],
            binLabel(b),
            b.n.toLocaleString(lang),
            `${b.imp_p0}%`,
            `${b.emp_p0}%`,
            `${b.imp_p2plus}%`,
            `${b.emp_p2plus}%`,
            `${b.d_p0_lo} to ${b.d_p0_hi}${pts}`,
          ]),
        ),
      }}
    >
      <p className="article-figure-legend">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </p>
      <div className="article-figure-multiples article-figure-multiples-2">
        {(["STL", "BLK"] as const).map((st) => (
          <div key={st}>
            <p className="article-figure-panel">
              {STAT[lang][st]}
              {lang === "en" ? " (percentage points)" : "（ポイント）"}
            </p>
            <Bars
              data={rows(data.bins[st])}
              series={series}
              legend={false}
              decimals={1}
              domain={[-4, 6]}
              valueTicks={[-4, -2, 0, 2, 4, 6]}
              refLine={0}
              valueLabels={false}
              xLabel={t.x}
              height={240}
            />
          </div>
        ))}
      </div>
    </Figure>
  );
}

export function TailFixFigure({ n, lang }: { n: number; lang: Lang }) {
  const arm = lang === "en" ? { poisson: "Plain rate", isotonic: "Flexible fix" } : { poisson: "期待値のみ", isotonic: "柔軟な補正" };
  const rows = data.tail.map((x) => ({
    label: `${arm[x.arm as "poisson" | "isotonic"]} · ${STAT[lang][x.stat as "STL" | "BLK"]}`,
    mean: x.gap,
    lo: x.lo,
    hi: x.hi,
    color: x.arm === "poisson" ? C.neutral : C.accent,
  }));
  const t =
    lang === "en"
      ? {
          title: "A flexible correction for the tails: average miss on the share of 2+ games",
          caption: `For players expected to get at least one steal or block, how far the predicted share of 2+ games was from reality. Dots are the average over three seasons × three seeds; lines run from best run to worst. The fix doubled the miss for steals and left blocks no better on average, and its overall error score was worse in ${data.tail_brier_worse} of ${data.tail_runs} runs. We kept the plain rate.`,
          head: ["Method", "Stat", "Avg miss (pts)", "Best run", "Worst run"],
          x: "Average miss on the 2+ share (points)",
          source: "HoopModel experiment: correction fitted on a held-back slice of each training season, scored on the test season.",
        }
      : {
          title: "分布の端を柔軟に補正した場合：2回以上の試合の割合の平均誤差",
          caption: `期待値が1回以上の選手について、2回以上の試合の予測割合が実際とどれだけずれたかを示しています。点は3シーズン×3シードの平均、線は最も良かった回から最も悪かった回までの範囲です。補正するとスティールではずれが倍になり、ブロックでも平均では改善せず、全体の誤差スコアも${data.tail_runs}回中${data.tail_brier_worse}回で悪化しました。そのため、期待値だけの方法を続けています。`,
          head: ["方法", "スタッツ", "平均誤差（ポイント）", "最良の回", "最悪の回"],
          x: "平均誤差（ポイント）",
          source: "HoopModel の検証実験：補正は各学習シーズンの一部を取り分けて作成し、テストシーズンで採点。",
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
        rows: data.tail.map((x) => [
          arm[x.arm as "poisson" | "isotonic"],
          STAT[lang][x.stat as "STL" | "BLK"],
          x.gap.toFixed(1),
          x.lo.toFixed(1),
          x.hi.toFixed(1),
        ]),
      }}
    >
      <RangeChart rows={rows} decimals={1} domain={[0, 9]} ticks={[0, 3, 6, 9]} xLabel={t.x} labelWidth={lang === "en" ? 140 : 140} />
    </Figure>
  );
}
