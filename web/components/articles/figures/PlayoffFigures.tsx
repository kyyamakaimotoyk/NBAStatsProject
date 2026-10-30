import data from "@/data/articles/playoff-predictability.json";
import Figure from "./Figure";
import { Bars } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const PHASE = {
  en: { regular: "Late regular season", playoffs: "Playoffs" },
  ja: { regular: "レギュラーシーズン終盤", playoffs: "プレーオフ" },
};

const SOURCE = {
  en: "HoopModel experiment, five seasons (2022–2026): models trained only on regular-season games before each season's playoffs, five seeds. Late regular season = the last three weeks before the playoffs.",
  ja: "HoopModel の検証実験、5シーズン（2022〜2026年）。各シーズンのプレーオフ前のレギュラーシーズンの試合だけで学習し、シード値5通り。レギュラーシーズン終盤＝プレーオフ前の最後の3週間。",
};

const MODEL = { rf: "Random Forest", xgb: "XGBoost" };
const MODEL_JA = { rf: "ランダムフォレスト", xgb: "XGBoost" };

function byModel(metric: "acc" | "auc" | "cov90", scale = 1) {
  return (["rf", "xgb"] as const).map((m) => {
    const get = (phase: string) => data.metrics.find((x) => x.model === m && x.phase === phase)!;
    return { model: m, regular: get("regular")[metric] * scale, playoffs: get("playoffs")[metric] * scale };
  });
}

export function PlayoffMetricsFigure({ n, lang }: { n: number; lang: Lang }) {
  const p = PHASE[lang];
  const names = lang === "en" ? MODEL : MODEL_JA;
  const series = [
    { key: "regular", name: p.regular, color: C.neutral },
    { key: "playoffs", name: p.playoffs, color: C.accent },
  ];
  const label = (rows: ReturnType<typeof byModel>) => rows.map((r) => ({ ...r, label: names[r.model] }));
  const t =
    lang === "en"
      ? {
          title: "Same models, three report cards: regular season vs playoffs",
          acc: "Winner accuracy",
          auc: "Ranking quality (AUC × 100)",
          cov: "90% margin ranges: share containing the real margin",
          caption:
            "Accuracy drops about 7 points and AUC loses more than half its edge over guessing (dashed line at 50), but the 90% margin ranges keep covering the real result about 90% of the time (dashed line at 90). The models get less decisive in the playoffs without getting less honest.",
          head: ["Model", "Games", "Accuracy", "AUC", "90% range coverage", "Avg margin miss"],
        }
      : {
          title: "同じモデルの3つの成績表：レギュラーシーズンとプレーオフ",
          acc: "勝敗的中率",
          auc: "勝率による並べ方の質（AUC×100）",
          cov: "点差の90%予測幅に実際の点差が入った割合",
          caption:
            "的中率は約7ポイント下がり、AUCは当てずっぽう（破線の50）に対する上乗せを半分以上失います。それでも点差の90%予測幅は、実際の結果を約90%（破線の90）の割合で捉え続けています。プレーオフでモデルの判断は鈍くなりますが、不確かさの示し方は正直なままです。",
          head: ["モデル", "試合数", "的中率", "AUC", "90%予測幅の的中", "平均点差誤差"],
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
        rows: data.metrics.map((m) => [
          `${names[m.model as "rf" | "xgb"]} · ${p[m.phase as "regular" | "playoffs"]}`,
          m.n,
          `${m.acc}%`,
          m.auc.toFixed(3),
          `${m.cov90}%`,
          m.mae,
        ]),
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
      <div className="article-figure-multiples">
        <div>
          <p className="article-figure-panel">{t.acc}</p>
          <Bars data={label(byModel("acc"))} series={series} legend={false} decimals={0} unit="%" domain={[0, 100]} refLine={50} height={220} />
        </div>
        <div>
          <p className="article-figure-panel">{t.auc}</p>
          <Bars data={label(byModel("auc", 100))} series={series} legend={false} decimals={0} domain={[0, 100]} refLine={50} height={220} />
        </div>
        <div>
          <p className="article-figure-panel">{t.cov}</p>
          <Bars data={label(byModel("cov90"))} series={series} legend={false} decimals={0} unit="%" domain={[0, 100]} refLine={90} height={220} />
        </div>
      </div>
    </Figure>
  );
}

export function MatchupGapFigure({ n, lang }: { n: number; lang: Lang }) {
  const p = PHASE[lang];
  const buckets = ["50-60", "60-70", "70-80", "80+"];
  const get = (phase: string, b: string) => data.favourite.find((f) => f.phase === phase && f.bucket === b)!;
  const rows = buckets.map((b) => ({
    label: b === "80+" ? "80%+" : `${b.replace("-", "–")}%`,
    regular: get("regular", b).pct,
    playoffs: get("playoffs", b).pct,
  }));
  const med = { regular: get("regular", "median").pct, playoffs: get("playoffs", "median").pct };
  const t =
    lang === "en"
      ? {
          title: "How lopsided are the matchups? The favorite's pre-game win probability",
          caption: `Win probability for the stronger side from a running Elo team rating, before each game. In the last weeks of the regular season a quarter of games have a favorite above 80%; in the playoffs it's ${get("playoffs", "80+").pct}%. The typical favorite drops from ${med.regular}% to ${med.playoffs}%. Mismatches are where models earn their accuracy, and the playoffs remove most of them.`,
          head: ["Favorite's win probability", p.regular, p.playoffs],
          x: "Favorite's pre-game win probability",
          y: "Share of games",
        }
      : {
          title: "対戦の実力差はどれくらいか：試合前の本命の勝率",
          caption: `試合ごとに更新されるイロレーティングから求めた、試合前の本命側の勝率です。レギュラーシーズン終盤は4試合に1試合で本命の勝率が80%を超えますが、プレーオフでは${get("playoffs", "80+").pct}%にとどまります。本命の勝率の中央値も${med.regular}%から${med.playoffs}%に下がります。モデルが的中率を稼ぐのは実力差のある対戦で、プレーオフではそれがほとんどなくなるのです。`,
          head: ["本命の勝率", p.regular, p.playoffs],
          x: "試合前の本命の勝率",
          y: "試合の割合",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{ head: t.head, rows: rows.map((r) => [r.label, `${r.regular}%`, `${r.playoffs}%`]) }}
    >
      <Bars
        data={rows}
        unit="%"
        domain={[0, 50]}
        xLabel={t.x}
        yLabel={t.y}
        series={[
          { key: "regular", name: p.regular, color: C.neutral },
          { key: "playoffs", name: p.playoffs, color: C.accent },
        ]}
      />
    </Figure>
  );
}
