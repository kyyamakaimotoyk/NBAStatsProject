import data from "@/data/articles/signal-or-noise.json";
import Figure from "./Figure";
import { Bars, RangeChart } from "./charts";
import { ARTICLE_COLORS as C } from "./colors";

type Lang = "en" | "ja";

const CONFIG = {
  en: { base: "Baseline", elo: "+ Elo", oppadj: "+ Opp-adjusted", lineup: "+ Lineups", tuning: "Tuned settings" },
  ja: { base: "元のモデル", elo: "＋イロ", oppadj: "＋相手補正", lineup: "＋ラインナップ", tuning: "調整後の設定" },
} as const;
type ConfigKey = keyof (typeof CONFIG)["en"];

const STAT_LABEL: Record<string, string> = { FG3M: "3PM", FG3A: "3PA" };
const stat = (s: string) => STAT_LABEL[s] ?? s;

const SOURCE = {
  en: "HoopModel experiments. Accuracy and splits: one 230-game test month (March–April 2026), 10 training seeds, 1,000 resamples per seed. Player tuning: three seasons, three seeds each.",
  ja: "HoopModel の検証実験。的中率と予測の分かれ方：230試合のテスト期間（2026年3〜4月）、シード値10通り、シードごとに1,000回のリサンプリング。選手モデルの調整：3シーズン、各3シード。",
};

export function NoiseRangesFigure({ n, lang }: { n: number; lang: Lang }) {
  const names = CONFIG[lang];
  const rows = data.ranges.map((r) => ({
    label: `${names[r.config as ConfigKey]} · ${r.model.toUpperCase()}`,
    mean: r.mean,
    lo: r.lo,
    hi: r.hi,
    color: r.model === "rf" ? C.rf : C.xgb,
  }));
  const t =
    lang === "en"
      ? {
          title: "Four versions of the team model, scored on the same 230 games",
          caption:
            "Dots are winner accuracy averaged over 10 training seeds; each line spans the middle 95% of results from resampling the test games. Every range overlaps every other, so on a month of games these versions can't be told apart by accuracy alone.",
          head: ["Version", "Model", "Accuracy", "95% range"],
          x: "Winner accuracy",
        }
      : {
          title: "チームモデルの4つのバージョンを、同じ230試合で採点",
          caption:
            "点はシード値10通りで平均した勝敗的中率、線はテスト試合をリサンプリングしたときの結果の中央95%の範囲です。どの範囲も互いに重なっており、1か月分の試合の的中率だけでは、どのバージョンが優れているか判別できません。",
          head: ["バージョン", "モデル", "的中率", "95%の範囲"],
          x: "勝敗的中率",
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
        rows: data.ranges.map((r) => [
          names[r.config as ConfigKey],
          r.model.toUpperCase(),
          `${r.mean}%`,
          `${r.lo}–${r.hi}%`,
        ]),
      }}
    >
      <RangeChart rows={rows} unit="%" domain={[65, 85]} xLabel={t.x} labelWidth={lang === "en" ? 140 : 120} />
    </Figure>
  );
}

export function DisagreementFigure({ n, lang }: { n: number; lang: Lang }) {
  const names = CONFIG[lang];
  const rows = data.splits.map((s) => ({
    label: `${names[s.change as ConfigKey]} (${s.model.toUpperCase()})`,
    new: s.new,
    old: s.old,
  }));
  const t =
    lang === "en"
      ? {
          title: "Games where the old and new versions picked different winners",
          caption:
            "A real improvement shows up as a lopsided split, run after run. None of these is conclusive on its own: even Elo's 8–3 could happen by chance about one time in four (p = 0.23). Elo was kept because its ranking quality also improved on a paired test; the tuned settings split exactly 7–7.",
          newName: "New version right",
          oldName: "Old version right",
          head: ["Change", "New version right", "Old version right", "p (McNemar)"],
          x: "Games",
        }
      : {
          title: "新旧バージョンで予測した勝者が分かれた試合",
          caption:
            "本物の改善なら、何度試しても勝ち負けが一方に偏ります。ここに挙げた結果は、どれも単独では決め手になりません。イロの8対3でさえ、偶然でも4回に1回ほどは起こる差です（p = 0.23）。イロを採用したのは、勝率による試合の並べ方も対応のある検定で改善したためです。調整後の設定は、きっかり7対7でした。",
          newName: "新バージョンが正解",
          oldName: "旧バージョンが正解",
          head: ["変更", "新バージョンが正解", "旧バージョンが正解", "p値（マクネマー検定）"],
          x: "試合数",
        };
  return (
    <Figure
      n={n}
      lang={lang}
      title={t.title}
      caption={t.caption}
      source={SOURCE[lang]}
      table={{ head: t.head, rows: data.splits.map((s, i) => [rows[i].label, s.new, s.old, s.p]) }}
    >
      <Bars
        data={rows}
        horizontal
        decimals={0}
        height={rows.length * 46 + 70}
        labelWidth={lang === "en" ? 140 : 120}
        xLabel={t.x}
        series={[
          { key: "new", name: t.newName, color: C.accent },
          { key: "old", name: t.oldName, color: C.neutral },
        ]}
      />
    </Figure>
  );
}

export function PlayerTuningFigure({ n, lang }: { n: number; lang: Lang }) {
  const rows = data.player_tuning.map((s) => ({
    label: stat(s.stat),
    mean: s.pct,
    lo: s.lo,
    hi: s.hi,
    color: s.keep ? C.accent : C.neutral,
  }));
  const t =
    lang === "en"
      ? {
          title: "Player model: change in average error after tuning, by stat",
          caption:
            "Left of zero means smaller errors. Dots are the average over three test seasons and three seeds; lines run from the best run to the worst. Orange stats cleared the pre-set bar. Turnovers improved too little to count, and blocks got slightly worse, so blocks alone kept the original settings.",
          head: ["Stat", "Avg change in error", "Best run", "Worst run", "Cleared the bar"],
          yes: "Yes",
          no: "No",
          x: "Change in average error",
        }
      : {
          title: "選手モデル：設定の調整による平均誤差の変化（スタッツ別）",
          caption:
            "0より左は誤差が小さくなったことを表します。点は3つのテストシーズン×3シードの平均、線は最も良かった回から最も悪かった回までの範囲です。オレンジは事前に決めた合格ラインを越えたスタッツです。ターンオーバー（TOV）は改善幅が小さすぎて合格に届かず、ブロック（BLK）はわずかに悪化したため、ブロックだけ元の設定を残しました。",
          head: ["スタッツ", "平均誤差の変化（平均）", "最良の回", "最悪の回", "合格"],
          yes: "○",
          no: "×",
          x: "平均誤差の変化",
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
        rows: data.player_tuning.map((s) => [
          stat(s.stat),
          `${s.pct.toFixed(2)}%`,
          `${s.lo.toFixed(2)}%`,
          `${s.hi.toFixed(2)}%`,
          s.keep ? t.yes : t.no,
        ]),
      }}
    >
      <RangeChart rows={rows} unit="%" decimals={2} refLine={0} xLabel={t.x} labelWidth={52} />
    </Figure>
  );
}
