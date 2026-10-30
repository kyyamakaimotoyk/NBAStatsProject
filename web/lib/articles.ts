// Registry for /articles. Each entry's body lives in components/articles/<slug>.tsx
// and is wired up in app/articles/[slug]/page.tsx (BODIES). Newest first.
//
// Disclosure line for everything published here: questions, methods, verdicts
// and effect sizes are fine; exact feature lists/counts, hyperparameter values,
// the injury/availability feature design, and pipeline internals are not.
//
// Figures rule: if an article argues from data, it shows the data. At least one
// figure per article, built from real results by scripts/build_article_figures.py
// (web/data/articles/<slug>.json) and drawn with components/articles/figures/.
// Full rule in docs/articles.md.

export type Article = {
  slug: string;
  date: string; // YYYY-MM-DD, publication date
  readMinutes: number;
  title: { en: string; ja: string };
  summary: { en: string; ja: string };
  // false = body is English-only for now; Japanese readers see a notice
  // (and the index tags it). Keep in sync with BODIES[slug].ja.
  hasJapanese: boolean;
};

export const ARTICLES: Article[] = [
  {
    slug: "minutes-and-misses",
    date: "2026-10-30",
    readMinutes: 5,
    title: {
      en: "Minutes explain only a sixth of a player's scoring miss",
      ja: "得点予測の外れのうち、出場時間で説明できるのは6分の1だけ",
    },
    summary: {
      en: "When a points projection misses, playing time gets the blame. We handed the model the real minutes after the fact and only about a sixth of the miss went away. What that says about reading projections.",
      ja: "得点予測が外れると、出場時間のせいにされがちです。試合後に実際の出場時間をモデルに渡してみると、消えた誤差は約6分の1だけでした。そこから見える、予測の読み方を紹介します。",
    },
    hasJapanese: true,
  },
  {
    slug: "count-stats",
    date: "2026-10-30",
    readMinutes: 5,
    title: {
      en: "Why we predict steals and blocks as chances, not numbers",
      ja: "スティールとブロックを、数字ではなく確率で予測する理由",
    },
    summary: {
      en: "Nobody gets 0.7 steals. We turn each projection into the chance of 0, 1 or 2+, and three seasons of results show it works for typical players, slips for the busiest shot-blockers, and resists an easy fix.",
      ja: "0.7回スティールする選手はいません。予測を0回・1回・2回以上の確率に変換する方法は、3シーズン分の結果を見ると、平均的な選手ではうまくいき、リーグ屈指のショットブロッカーではずれ、簡単な補正では直りませんでした。",
    },
    hasJapanese: true,
  },
  {
    slug: "player-baselines",
    date: "2026-10-30",
    readMinutes: 6,
    title: {
      en: "The simple baseline that wasn't: testing our player projections",
      ja: "手ごわいはずの基準は、そうでもなかった：選手の成績予測の検証",
    },
    summary: {
      en: "Before launch, our player model had to beat two simple methods. The famous one, Marcel, lost to a plain 10-game average on most stats. Our model beat both almost everywhere, with two honest exceptions.",
      ja: "公開前、選手の成績予測モデルは2つの単純な方法に勝つ必要がありました。有名なMarcelは、ほとんどのスタッツで直近10試合の平均に負けました。モデルはほぼすべてで両方に勝ちましたが、正直に書いておくべき例外が2つあります。",
    },
    hasJapanese: true,
  },
  {
    slug: "win-probability",
    date: "2026-10-30",
    readMinutes: 6,
    title: {
      en: "What a 70% win probability actually means, and the fix that broke our picks",
      ja: "「勝率70%」の本当の意味と、予測を壊してしまった修正",
    },
    summary: {
      en: "A win probability is a promise about frequencies. We added a layer to make ours more honest, and for two months it made one model pick the home team in every game. What we learned, and what we do now.",
      ja: "勝率は、頻度についての約束です。その数字をより正直にするための層を加えたところ、2か月にわたって1つのモデルがすべての試合でホームチームを予測するようになりました。そこから学んだことと、現在の運用を紹介します。",
    },
    hasJapanese: true,
  },
  {
    slug: "early-season",
    date: "2026-10-30",
    readMinutes: 5,
    title: {
      en: "Early-season picks are weaker, and so is the betting market's",
      ja: "シーズン序盤の予測が当たりにくいのは、賭け市場も同じ",
    },
    summary: {
      en: "October is the hardest month of the season for our models and for the betting market. Three seasons of results show why, and why feeding the models more old data wouldn't fix it.",
      ja: "10月は、当サイトのモデルにとっても賭け市場にとっても、1年で最も予測が難しい月です。3シーズン分の結果からその理由と、古いデータを増やしても解決しない理由を見ていきます。",
    },
    hasJapanese: true,
  },
  {
    slug: "signal-or-noise",
    date: "2026-10-27",
    readMinutes: 6,
    title: {
      en: "Signal or noise? How we decide whether a model change is real",
      ja: "その改善は本物か？ モデル変更を採用するかどうかの判断基準",
    },
    summary: {
      en: "A new feature that 'adds 2.6 points of accuracy' on a month of games usually adds nothing. Here is the testing routine that caught it, and the one change it let through.",
      ja: "1か月分の試合で「的中率が2.6ポイント上がった」新しい特徴量は、たいてい何も改善していません。それを見抜いた検証の手順と、検証を通過した唯一の変更を紹介します。",
    },
    hasJapanese: true,
  },
  {
    slug: "margin-floor",
    date: "2026-10-27",
    readMinutes: 5,
    title: {
      en: "Why nobody predicts NBA margins within five points",
      ja: "NBAの点差を5点以内で当てられる人がいない理由",
    },
    summary: {
      en: "Our models miss the final margin by about 11.6 points on average, and the betting market by about 10.8. That isn't a bug. Here's how much of an NBA margin is predictable at all.",
      ja: "モデルの平均点差誤差は約11.6点、賭け市場でも約10.8点です。これは欠陥ではありません。NBAの点差のうち、そもそも予測できる部分はどれくらいなのかを考えます。",
    },
    hasJapanese: true,
  },
  {
    slug: "impact-ratings",
    date: "2026-10-27",
    readMinutes: 6,
    title: {
      en: "Last season's impact ratings don't help predict this season",
      ja: "前シーズンの選手インパクト指標は、今シーズンの予測に役立たない",
    },
    summary: {
      en: "All-in-one player impact metrics look like an obvious input. We tested them twice, in the player model and the team model, and both times they added nothing the models didn't already know.",
      ja: "選手の総合インパクト指標は、一見すると予測に欠かせない材料に思えます。選手モデルとチームモデルの両方で検証しましたが、どちらもモデルがすでに持っている以上の情報はありませんでした。",
    },
    hasJapanese: true,
  },
  {
    slug: "playoff-predictability",
    date: "2026-10-27",
    readMinutes: 5,
    title: {
      en: "Playoff games are harder to predict, and it's not the model's fault",
      ja: "プレーオフの勝敗予測が難しいのは、モデルのせいではない",
    },
    summary: {
      en: "Trained on the regular season, our models lose about 7 points of winner accuracy in the playoffs, yet their margin ranges stay just as honest. What changes when the postseason starts.",
      ja: "レギュラーシーズンで学習したモデルは、プレーオフになると勝敗的中率が約7ポイント下がります。それでも点差の予測幅は信頼できるままです。ポストシーズンで何が変わるのかを見ていきます。",
    },
    hasJapanese: true,
  },
];

export function getArticle(slug: string): Article | undefined {
  return ARTICLES.find((a) => a.slug === slug);
}
