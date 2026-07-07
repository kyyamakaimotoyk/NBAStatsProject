// English/Japanese UI dictionaries. `en` defines the shape; `ja` is type-checked
// against it, so a missing translation is a build error.
//
// Japanese style guide (edit this glossary and the strings will follow):
//   stat(s)            → 統計値（スタッツとしない）
//   prediction / pick  → 予想
//   winner accuracy    → 勝敗的中率
//   margin             → 点差 / average margin miss → 平均点差誤差
//   graded             → 採点済み
//   market closing line→ 市場のクロージングライン
//   trendline (OLS)    → 回帰直線 / rolling average → 移動平均
//   register           → 丁寧体（です・ます）。直訳調・過剰なカタカナ語は避ける。
// Team codes, stat keys (PTS, FG_PCT, …) and dates stay untranslated by design.

export type Lang = "en" | "ja";

const en = {
  nav: {
    tonight: "Tonight",
    trackRecord: "Track record",
    modelLab: "Model lab",
    explore: "Explore",
    scatter: "Scatter",
    drivers: "What wins games",
    about: "About",
  },

  footer: {
    disclaimer: "Predictions are machine-learning model output, not betting advice.",
  },

  common: {
    plusMinusPts: (v: string) => `±${v} pts`,
  },

  models: {
    rf: "Random Forest",
    nn: "Neural Net",
    xgb: "XGBoost",
  } as Record<string, string>,

  charts: {
    notEnoughData: "Not enough data in this window yet.",
    gameDate: "Game date",
    winnerAccuracyY: "Winner accuracy",
    marginMissY: "Average margin miss (pts)",
    dailyWinnerAccuracyY: "Daily winner accuracy",
    actualHomeWinRateY: "Actual home-win rate",
    rocNotEnough: "Not enough graded games for a ROC curve yet.",
    rocXLabel: "False positive rate (called home win, away won)",
    rocYLabel: "True positive rate",
    corrXLabel: "Correlation with final margin",
  },

  home: {
    heroTitle: "Nightly NBA predictions — with receipts.",
    heroSub:
      "Three machine-learning models pick every NBA game. Every prediction is logged, scored against the real result, and published — hits and misses alike.",
    ctaTonight: "Tonight's picks",
    ctaRecord: "See the track record",
    windowLast30: "last 30 days",
    windowLastSeason: "last season",
    proofWinners: (window: string) => `winners called, ${window}`,
    proofMarginLine1: "average margin miss,",
    proofLoggedLine1: "predictions logged",
    proofLoggedLine2: "and publicly scored",
    errLoad: (e: string) => `Couldn't load predictions: ${e}`,
    loading: "Loading predictions…",
    offseasonTitle: "It's the offseason",
    offseasonBody:
      "Nightly picks return when the season tips off in October. Until then, the whole track record stays up — every prediction we've made, scored against what actually happened.",
    offseasonLinkRecord: "Last season's report card →",
    offseasonLinkExplore: "Explore the data →",
    latestSlate: (date: string) => `Latest slate — ${date}`,
    predictionsFor: (date: string) => `Predictions for ${date}`,
    staleNote: "No games tonight — this is the most recent slate the models predicted.",
    howTitle: "How it works",
    step1Title: "Box scores in",
    step1Body: "Every game's team stats — shooting, rebounding, hustle, tracking.",
    step2Title: "Rolling form",
    step2Body: "Each team's recent play, distilled into rolling features.",
    step3Title: "Three models",
    step3Body:
      "A random forest, gradient boosting and a neural net each pick a winner and a margin.",
    step4Title: "Scored in public",
    step4Body: "Picks post nightly, then get graded against the final score.",
    step4Link: "The full record →",
    longerVersion: "Want the longer version — data, models, the nightly cycle?",
    howLink: "How HoopModel works →",
  },

  predTable: {
    matchup: "Matchup",
    model: "Model",
    pick: "Pick",
    winProb: "Win prob.",
    margin: "Margin",
    final: "Final",
    result: "Result",
    coinFlip: "coin flip",
    byMargin: (n: string) => `by ${n}`,
  },

  injury: {
    title: (date: string) => `Injury report — ${date}`,
    subtitle:
      "The NBA's official pre-game injury report for this slate. The models see this too — player availability feeds the prediction features.",
    statuses: {
      Out: "Out",
      Doubtful: "Doubtful",
      Questionable: "Questionable",
      Probable: "Probable",
      Available: "Available",
    } as Record<string, string>,
  },

  accuracy: {
    title: "Track record",
    subtitle:
      "Every prediction is logged before tip-off and graded after the final buzzer. This page is the full scoreboard — nothing is edited after the fact.",
    errLoad: (e: string) => `Couldn't load the track record: ${e}`,
    loading: "Loading the track record…",
    windowLabel: "Window:",
    modelLabel: "Model:",
    windows: [
      { days: 30, label: "Last 30 days" },
      { days: 90, label: "Last 90 days" },
      { days: 365, label: "Last 12 months" },
      { days: 1100, label: "Three seasons" },
    ],
    noGraded: "No graded games in this window yet.",
    cardWinnerAcc: "Winner accuracy",
    cardWinnerSub: (model: string) => `${model} · a coin flip is 50%`,
    cardMarginMiss: "Average margin miss",
    cardMarginSub: "how far the predicted margin lands from the real one",
    cardMarket: "Market closing line",
    cardMarketSub: (modelMae: string, n: string, total: string, closerPct: number) =>
      `vs our ±${modelMae} — paired on the ${n} of ${total} graded games with a line · we were closer on ${closerPct}%`,
    cardGraded: "Games graded",
    cardGradedSub: "in this window",
    marketSeries: "Market closing line",
    clsTitle: "Winner classification — market vs the models",
    clsCaption:
      "Everyone judged on the same footing: graded games that have a closing line. The market's pick is its favorite (pick'em lines make no call and are excluded). The dashed line is 50% — coin-flip territory. Hover or tap a bar for the game count.",
    marketFavorite: "Market favorite",
    recentPicks: (model: string) => `Recent picks — ${model}`,
    picksCaption: (n: number) =>
      `The last ${n} graded picks, oldest to newest. Tap a square for the game.`,
    accOverTime: "Winner accuracy over time",
    accCaption:
      "Each point is the trailing 7 days of games. The light dashed line is the market favorite's hit rate on the same games; the 50% line is coin-flip territory.",
    maeOverTime: "Margin error over time",
    maeCaption:
      "Average points missed by, trailing 7 days — lower is better. The dashed line is the betting market's closing spread on the same games: the strongest public benchmark for a game's margin. We show it to keep ourselves honest, not to sell picks.",
    predVsActual: "Predicted vs actual margin",
    scatterCaption:
      "One point per game (home-team perspective). On the dashed diagonal, the prediction was exact; green points are games where the winner was still called correctly.",
    homeAway: "Home picks vs away picks",
    pickHome: "When we pick the home team",
    pickAway: "When we pick the away team",
    correctAcross: (n: number) => `correct, across ${n} picks`,
    homeAwayCaption:
      "A sanity check on home-court bias: if the model only ever trusted home teams, the away column would collapse.",
  },

  perf: {
    title: "Model performance",
    subtitle:
      "How each model has actually done on completed games — accuracy, calibration, and the game-by-game record.",
    windows: [
      { days: 30, label: "30 days" },
      { days: 90, label: "90 days" },
      { days: 180, label: "180 days" },
      { days: 365, label: "Full season" },
      { days: 1100, label: "3 seasons" },
    ],
    windowLabel: "Window:",
    errLoad: (e: string) => `Couldn't load performance: ${e}`,
    loading: "Loading performance…",
    noCompleted: "No completed games in this window yet.",
    accuracyGames: (n: number) => `accuracy · ${n} games`,
    maeCalib: (mae: string, calib: string) => `MAE ${mae} · calib err ${calib}`,
    dailyAcc: "Daily win-prediction accuracy",
    calibration: "Calibration — predicted win prob vs. actual home-win rate",
    calibXLabel: "Predicted home win %",
    roc: "ROC — how cleanly each model separates home wins from losses",
    rocCaption:
      'How to read: each point along a curve is a different confidence cutoff for calling "home win." The higher a curve bows above the dashed diagonal (coin-flip), the better that model ranks games — AUC 0.5 is no skill, 1.0 is perfect. Unlike accuracy, this scores the probabilities, not just the picks.',
    confusion: "Confusion matrix — where the misses live",
    confusionCaption:
      "How to read: rows are what actually happened, columns are what the model picked. The two green diagonal cells are correct calls; off-diagonal are mistakes. TN = correctly called an away win, TP = correctly called a home win, FP = picked home but away won, FN = picked away but home won. Comparing FP vs FN shows whether a model leans too hard on home court.",
    gameByGame: "Game-by-game results",
    resultsCaption:
      'Every game in the selected window, newest first — scroll within the table. Each model\'s cell shows its pick and projected margin, tinted by whether the pick was right; hover a cell for the win probability. "—" means that model logged no prediction for the game.',
  },

  confMatrix: {
    pickedAway: "Picked away",
    pickedHome: "Picked home",
    awayWon: "Away won",
    homeWon: "Home won",
  },

  resultsTable: {
    date: "Date",
    matchup: "Matchup",
    final: "Final",
    cellTitle: (winner: string, pct: number, coin: boolean) =>
      `${winner} at ${pct}% win probability${coin ? " (coin flip)" : ""}`,
    cellPick: (team: string, margin: string) => `${team} by ${margin}`,
  },

  picksStrip: {
    aria: (n: number) => `Last ${n} graded picks`,
    chipTitle: (date: string, away: string, home: string, pick: string) =>
      `${date} — ${away} @ ${home}: picked ${pick}`,
    detailPicked: "picked",
    detailFinal: (score: string) => ` · final ${score}`,
    detailWon: (winner: string) => ` · ${winner} won`,
    hit: "hit",
    miss: "miss",
  },

  drivers: {
    title: "What wins games",
    subtitle:
      "How strongly each rolling team stat correlates with a game's final margin. Positive = more of it tends to go with winning.",
    sideLabel: "Side:",
    sideDiff: "Differential (home − away)",
    sideHome: "Home team",
    sideAway: "Away team",
    windowLabel: "Window:",
    last5: "Last 5",
    last10: "Last 10",
    topLabel: "Top:",
    errLoad: (e: string) => `Couldn't load: ${e}`,
    loading: "Loading…",
    noData: "No correlation data available.",
    strongestPos: "Strongest positive:",
    strongestNeg: "strongest negative:",
    featureCounts: (n1: number, n2: number, total: number) =>
      `${n1} stats with |r| > 0.1, ${n2} with |r| > 0.2 (of ${total}).`,
    topHeading: (n: number) => `Top ${n} by |correlation| with margin`,
    noCorrelations: "No correlations available.",
  },

  explore: {
    title: "Explore the data",
    subtitle:
      "Track any team's rolling form (last 5 or 10 games) for a chosen stat across the season.",
    statLabel: "Stat:",
    windowLabel: "Window:",
    last5: "Last 5",
    last10: "Last 10",
    horizonLabel: "Range:",
    horizons: [
      { days: 90, label: "Last 90 days" },
      { days: 365, label: "1 season" },
      { days: 730, label: "2 seasons" },
      { days: 1100, label: "3 seasons" },
    ],
    teamsMulti: "Teams (check any number):",
    clearTeams: (n: number) => `Clear ${n} selected`,
    errLoad: (e: string) => `Couldn't load: ${e}`,
    loading: "Loading…",
    noStatData: "No data for this stat yet.",
    rollingHeading: (feature: string, window: string) =>
      `${feature} (${window}) — rolling average`,
    chartYLabel: (feature: string, window: string) => `${feature} (${window} rolling avg)`,
    pickTeam: "Pick at least one team.",
    noGamesInRange: "No games for these teams in range.",
    categories: {
      Traditional: "Traditional",
      Advanced: "Advanced",
      "Four Factors": "Four Factors",
      Hustle: "Hustle",
      Tracking: "Tracking",
      Misc: "Misc",
      Scoring: "Scoring",
    } as Record<string, string>,
  },

  scatter: {
    title: "Stat scatter",
    subtitle:
      "Every team-game as a point — pick two stats, color by win/loss, fit a trendline, and optionally filter to specific teams.",
    teamsOptional: "Teams (optional):",
    trendline: "Trendline",
    errLoad: (e: string) => `Couldn't load: ${e}`,
    loading: "Loading…",
    noSelection: "No points for this selection.",
    heading: (y: string, x: string, games: number, teams: number) =>
      `${y} vs ${x} — ${games} games${teams > 0 ? `, ${teams} team${teams > 1 ? "s" : ""}` : ""}`,
    win: "Win",
    loss: "Loss",
    winnerLabel: "Winner:",
    noPoints: "No points.",
    margCaption:
      "Box plots along each axis show the spread of that stat in each selected team's wins (green) and losses (red) — hover a box for min, quartiles, and median.",
    margCapNote: (n: number) => `Distributions are shown for the first ${n} selected teams.`,
    box: {
      max: "max",
      q3: "upper quartile",
      median: "median",
      q1: "lower quartile",
      min: "min",
      gamesLabel: (n: number) => `${n} games`,
    },
  },

  marginScatter: {
    xLabel: "Predicted home margin (pts)",
    yLabel: "Actual home margin (pts)",
    winnerCalled: "Winner called",
    missed: "Missed",
    picked: (pick: string) => `picked ${pick}`,
    predActual: (x: string, y: string) => `predicted ${x} · actual ${y}`,
    noGraded: "No graded games in this window yet.",
  },
};

export type Dict = typeof en;

const ja: Dict = {
  nav: {
    tonight: "今夜の予想",
    trackRecord: "的中実績",
    modelLab: "モデルラボ",
    explore: "データ探索",
    scatter: "散布図",
    drivers: "勝敗を分けるもの",
    about: "このサイトについて",
  },

  footer: {
    disclaimer:
      "本サイトの予想は機械学習モデルの出力であり、ベッティングを推奨するものではありません。",
  },

  common: {
    plusMinusPts: (v: string) => `±${v}点`,
  },

  models: {
    rf: "ランダムフォレスト",
    nn: "ニューラルネット",
    xgb: "勾配ブースティング",
  } as Record<string, string>,

  charts: {
    notEnoughData: "この期間は、まだデータが足りません。",
    gameDate: "試合日",
    winnerAccuracyY: "勝敗的中率",
    marginMissY: "平均点差誤差（点）",
    dailyWinnerAccuracyY: "日別的中率",
    actualHomeWinRateY: "実際のホーム勝率",
    rocNotEnough: "ROC曲線を描くには、採点済みの試合がまだ足りません。",
    rocXLabel: "偽陽性率（ホーム勝ちと予想して外れた割合）",
    rocYLabel: "真陽性率",
    corrXLabel: "最終点差との相関係数",
  },

  home: {
    heroTitle: "NBAの全試合を、毎晩予想。結果はすべて公開。",
    heroSub:
      "3つの機械学習モデルがNBAの全試合の勝敗を予想します。予想はすべて試合前に記録し、実際の結果と照らし合わせて採点したうえで、当たりも外れもそのまま公開しています。",
    ctaTonight: "今夜の予想を見る",
    ctaRecord: "これまでの成績を見る",
    windowLast30: "直近30日",
    windowLastSeason: "昨シーズン",
    proofWinners: (window: string) => `勝敗的中率（${window}）`,
    proofMarginLine1: "平均点差誤差",
    proofLoggedLine1: "これまでの予想数",
    proofLoggedLine2: "（全件を公開・採点）",
    errLoad: (e: string) => `予想を読み込めませんでした: ${e}`,
    loading: "予想を読み込んでいます…",
    offseasonTitle: "いまはオフシーズンです",
    offseasonBody:
      "毎晩の予想は、10月のシーズン開幕とともに再開します。オフシーズン中も、これまでのすべての予想と採点結果は引き続き公開しています。",
    offseasonLinkRecord: "昨シーズンの成績を見る →",
    offseasonLinkExplore: "データを見てみる →",
    latestSlate: (date: string) => `直近の予想 — ${date}`,
    predictionsFor: (date: string) => `${date}の予想`,
    staleNote: "今夜は試合がありません。直近に予想した試合を表示しています。",
    howTitle: "予想のしくみ",
    step1Title: "データを集める",
    step1Body:
      "毎試合のボックススコアを取り込みます。得点やリバウンドなどの基本統計値から、ハッスル・トラッキング系の指標まで。",
    step2Title: "直近の調子を数値化",
    step2Body: "各チームの最近の戦いぶりを、特徴量として数値化します。",
    step3Title: "3つのモデルが予想",
    step3Body:
      "ランダムフォレスト、勾配ブースティング、ニューラルネットが、それぞれ勝者と点差を予想します。",
    step4Title: "結果を公開採点",
    step4Body: "予想は毎晩掲載し、最終スコアと照らし合わせて採点します。",
    step4Link: "全記録を見る →",
    longerVersion: "データやモデル、毎晩の処理の流れをもっと詳しく知りたい方は:",
    howLink: "HoopModelのしくみ →",
  },

  predTable: {
    matchup: "対戦カード",
    model: "モデル",
    pick: "予想",
    winProb: "勝率",
    margin: "点差",
    final: "最終スコア",
    result: "結果",
    coinFlip: "五分五分",
    byMargin: (n: string) => `${n}点差`,
  },

  injury: {
    title: (date: string) => `インジャリーレポート — ${date}`,
    subtitle:
      "試合前にNBAが公表する公式の負傷者リストです。選手の出場可否はモデルにも入力され、予想に反映されます。",
    statuses: {
      Out: "欠場",
      Doubtful: "出場疑わしい",
      Questionable: "出場不透明",
      Probable: "出場濃厚",
      Available: "出場可",
    } as Record<string, string>,
  },

  accuracy: {
    title: "的中実績",
    subtitle:
      "すべての予想を試合前に記録し、試合終了後に採点しています。このページはその全成績表です。あとからの修正は一切ありません。",
    errLoad: (e: string) => `実績を読み込めませんでした: ${e}`,
    loading: "実績を読み込んでいます…",
    windowLabel: "期間:",
    modelLabel: "モデル:",
    windows: [
      { days: 30, label: "直近30日" },
      { days: 90, label: "直近90日" },
      { days: 365, label: "直近1年" },
      { days: 1100, label: "過去3シーズン" },
    ],
    noGraded: "この期間には、採点済みの試合がまだありません。",
    cardWinnerAcc: "勝敗的中率",
    cardWinnerSub: (model: string) => `${model}（コイン投げなら50%）`,
    cardMarginMiss: "平均点差誤差",
    cardMarginSub: "予想した点差と実際の点差のずれ",
    cardMarket: "市場のクロージングライン",
    cardMarketSub: (modelMae: string, n: string, total: string, closerPct: number) =>
      `当モデルは±${modelMae}。ラインのある${n}試合（採点済み${total}試合中）で比較すると、${closerPct}%の試合で当モデルの方が実際の点差に近い予想でした`,
    cardGraded: "採点済みの試合",
    cardGradedSub: "この期間の合計",
    marketSeries: "市場クロージングライン",
    clsTitle: "勝敗的中率 — 市場とモデルの比較",
    clsCaption:
      "公平な比較のため、クロージングラインが存在する採点済みの試合だけで集計しています。市場の「予想」はフェイバリット(ライン上有利とされた側)です。イーブン(ピックエム)の試合は予想なしとして除外しています。破線の50%はコイン投げと同じ水準です。バーをタップすると試合数が表示されます。",
    marketFavorite: "市場フェイバリット",
    recentPicks: (model: string) => `直近の予想 — ${model}`,
    picksCaption: (n: number) =>
      `直近${n}件の採点済み予想です(左から古い順)。マスをタップすると試合の詳細が表示されます。`,
    accOverTime: "勝敗的中率の推移",
    accCaption:
      "各点は、その日までの7日間の成績を示します。薄い破線は同じ試合における市場フェイバリットの的中率、50%の線はコイン投げと同じ水準です。",
    maeOverTime: "点差誤差の推移",
    maeCaption:
      "その日までの7日間で、予想が実際の点差から平均何点ずれていたかを示します(小さいほど優秀です)。破線は同じ試合に対するブックメーカーのクロージングスプレッドで、点差予想の基準としては最も厳しい公開ベンチマークです。自己評価のために掲載しているもので、予想の宣伝が目的ではありません。",
    predVsActual: "予想点差と実際の点差",
    scatterCaption:
      "1つの点が1試合を表します(ホームチーム視点)。破線の対角線上にある点は点差まで的中した予想です。緑の点は、点差は外れたものの勝者は的中した試合を示します。",
    homeAway: "ホーム予想とアウェイ予想",
    pickHome: "ホーム勝利と予想したとき",
    pickAway: "アウェイ勝利と予想したとき",
    correctAcross: (n: number) => `${n}件中の的中率`,
    homeAwayCaption:
      "ホーム側への偏りを確認するための項目です。モデルがホームチームばかりを選んでいれば、アウェイ側の的中率は大きく下がるはずです。",
  },

  perf: {
    title: "モデルの成績",
    subtitle:
      "終了した試合に対する各モデルの成績です。的中率、キャリブレーション、試合ごとの記録を確認できます。",
    windows: [
      { days: 30, label: "30日" },
      { days: 90, label: "90日" },
      { days: 180, label: "180日" },
      { days: 365, label: "1シーズン" },
      { days: 1100, label: "3シーズン" },
    ],
    windowLabel: "期間:",
    errLoad: (e: string) => `成績を読み込めませんでした: ${e}`,
    loading: "成績を読み込んでいます…",
    noCompleted: "この期間には、終了した試合がまだありません。",
    accuracyGames: (n: number) => `的中率（${n}試合）`,
    maeCalib: (mae: string, calib: string) => `平均誤差 ${mae}点 · 較正誤差 ${calib}`,
    dailyAcc: "日別の的中率",
    calibration: "キャリブレーション — 予想勝率どおりに勝っているか",
    calibXLabel: "予想ホーム勝率（%）",
    roc: "ROC曲線 — ホームの勝ち負けをどこまで見分けられるか",
    rocCaption:
      "見方: 曲線上の各点は、どこまで確信があれば「ホーム勝利」と判定するか、そのしきい値を変えたときの結果に対応します。曲線が破線の対角線(コイン投げと同等)より上に膨らむほど、そのモデルは勝敗の見極めに優れています。AUCは0.5で予測力なし、1.0で完全な予測です。的中率と異なり、予想の当たり外れではなく、出力された確率そのものを評価する指標です。",
    confusion: "混同行列 — どんな外し方をしているか",
    confusionCaption:
      "見方: 行が実際の結果、列がモデルの予想です。対角線上の緑の2マスが正解、残りの2マスが不正解です。TNはアウェイ勝利の的中、TPはホーム勝利の的中、FPはホーム勝利と予想して外れた試合、FNはアウェイ勝利と予想して外れた試合を表します。FPとFNを比較すると、モデルがホーム側に偏っていないかを確認できます。",
    gameByGame: "試合ごとの結果",
    resultsCaption:
      "選択した期間の全試合を新しい順に表示しています(表内をスクロールできます)。各モデルの欄には予想した勝者と点差を表示し、的中なら緑、外れなら赤の背景になります。カーソルを合わせると勝率が表示されます。「—」は、そのモデルがその試合を予想しなかったことを示します。",
  },

  confMatrix: {
    pickedAway: "アウェイと予想",
    pickedHome: "ホームと予想",
    awayWon: "アウェイが勝利",
    homeWon: "ホームが勝利",
  },

  resultsTable: {
    date: "日付",
    matchup: "対戦カード",
    final: "最終スコア",
    cellTitle: (winner: string, pct: number, coin: boolean) =>
      `${winner}が勝つ確率 ${pct}%${coin ? "（五分五分）" : ""}`,
    cellPick: (team: string, margin: string) => `${team} ${margin}点差`,
  },

  picksStrip: {
    aria: (n: number) => `直近${n}件の採点済み予想`,
    chipTitle: (date: string, away: string, home: string, pick: string) =>
      `${date} ${away} @ ${home}｜予想は${pick}`,
    detailPicked: "予想は",
    detailFinal: (score: string) => ` · 最終スコア ${score}`,
    detailWon: (winner: string) => ` · ${winner}が勝利`,
    hit: "的中",
    miss: "外れ",
  },

  drivers: {
    title: "勝敗を分けるもの",
    subtitle:
      "直近数試合の各統計値が、試合の最終点差とどの程度相関しているかを示します。相関が正であれば、その値が高いほど勝利につながりやすいことを意味します。",
    sideLabel: "対象:",
    sideDiff: "ホームとアウェイの差",
    sideHome: "ホームチーム",
    sideAway: "アウェイチーム",
    windowLabel: "期間:",
    last5: "直近5試合",
    last10: "直近10試合",
    topLabel: "表示件数:",
    errLoad: (e: string) => `読み込めませんでした: ${e}`,
    loading: "読み込んでいます…",
    noData: "相関データがまだありません。",
    strongestPos: "正の相関が最も強いのは",
    strongestNeg: "負の相関が最も強いのは",
    featureCounts: (n1: number, n2: number, total: number) =>
      `|r| > 0.1 の統計値は${n1}件、|r| > 0.2 は${n2}件です（全${total}件中）。`,
    topHeading: (n: number) => `点差との相関が強い統計値（上位${n}件）`,
    noCorrelations: "相関データがまだありません。",
  },

  explore: {
    title: "データ探索",
    subtitle:
      "統計値をひとつ選ぶと、各チームの調子（直近5試合または10試合の移動平均）がシーズンを通してどう推移したかを確認できます。",
    statLabel: "統計値:",
    windowLabel: "移動平均の幅:",
    last5: "直近5試合",
    last10: "直近10試合",
    horizonLabel: "期間:",
    horizons: [
      { days: 90, label: "直近90日" },
      { days: 365, label: "1シーズン" },
      { days: 730, label: "2シーズン" },
      { days: 1100, label: "3シーズン" },
    ],
    teamsMulti: "チーム（複数選択できます）:",
    clearTeams: (n: number) => `選択を解除（${n}チーム）`,
    errLoad: (e: string) => `読み込めませんでした: ${e}`,
    loading: "読み込んでいます…",
    noStatData: "この統計値のデータはまだありません。",
    rollingHeading: (feature: string, window: string) =>
      `${feature}の移動平均（${window}）`,
    chartYLabel: (feature: string, window: string) =>
      `${feature}（直近${window === "L5" ? 5 : 10}試合平均）`,
    pickTeam: "チームをひとつ以上選んでください。",
    noGamesInRange: "この期間に、選んだチームの試合はございません。",
    categories: {
      Traditional: "基本統計値",
      Advanced: "応用統計値",
      "Four Factors": "フォーファクター",
      Hustle: "ハッスル",
      Tracking: "トラッキング",
      Misc: "その他",
      Scoring: "得点内訳",
    } as Record<string, string>,
  },

  scatter: {
    title: "統計値の散布図",
    subtitle:
      "1チームの1試合がひとつの点になります。統計値を2つ選ぶと勝敗別に色分けして表示され、回帰直線の表示や、チームによる絞り込みもできます。",
    teamsOptional: "チームで絞り込み（任意）:",
    trendline: "回帰直線",
    errLoad: (e: string) => `読み込めませんでした: ${e}`,
    loading: "読み込んでいます…",
    noSelection: "この条件に当てはまる試合がございません。",
    heading: (y: string, x: string, games: number, teams: number) =>
      `${y} × ${x} — ${games}試合${teams > 0 ? `（${teams}チーム）` : ""}`,
    win: "勝ち",
    loss: "負け",
    winnerLabel: "勝者:",
    noPoints: "表示できる点がございません。",
    margCaption:
      "チームを選ぶと、縦軸・横軸それぞれに沿って、そのチームの勝ち試合（緑）と負け試合（赤）の統計値の分布を箱ひげ図で表示します。箱にカーソルを合わせると最小値・四分位数・中央値を確認できます。",
    margCapNote: (n: number) => `箱ひげ図は先に選んだ${n}チームまでの表示です。`,
    box: {
      max: "最大値",
      q3: "第3四分位数",
      median: "中央値",
      q1: "第1四分位数",
      min: "最小値",
      gamesLabel: (n: number) => `${n}試合`,
    },
  },

  marginScatter: {
    xLabel: "ホーム側の予想点差（点）",
    yLabel: "ホーム側の実際の点差（点）",
    winnerCalled: "勝者を的中",
    missed: "外れ",
    picked: (pick: string) => `予想は${pick}`,
    predActual: (x: string, y: string) => `予想 ${x} · 実際 ${y}`,
    noGraded: "この期間には、採点済みの試合がまだございません。",
  },
};

export const translations: Record<Lang, Dict> = { en, ja };
