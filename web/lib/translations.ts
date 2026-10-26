// English/Japanese UI dictionaries. `en` defines the shape; `ja` is type-checked
// against it, so a missing translation is a build error.
//
// Japanese style guide (edit this glossary and the strings will follow):
//   stat(s)            → スタッツ
//   prediction / pick  → 予測
//   winner accuracy    → 勝敗的中率
//   margin             → 点差 / average margin miss → 平均点差誤差
//   graded             → 採点済み
//   market closing line / closing spread → 市場の最終予想点差（クロージングライン・スプレッドとしない）
//   betting            → 賭け（ベッティングとしない）
//   even / pick'em     → 互角（イーブン・ピックエムとしない）
//   against the spread → 点差込みの採点（ATS）／push → 引き分け扱い（対スプレッド・プッシュとしない）
//   player projections → 選手の成績予測（プロジェクションとしない）。ファンタジー用語（ロスター・ウェイバー等）は慣用のカタカナ語のままでよい。
//   trendline (OLS)    → 回帰直線 / rolling average → 移動平均
//   register           → 丁寧体（です・ます）。直訳調・過剰なカタカナ語は避ける。
//   coin-toss          → 絶対にコイン投げ・コイントスと直訳しない、もっと自然な言い方で。
// Team codes, stat keys (PTS, FG_PCT, …) and dates stay untranslated by design.

export type Lang = "en" | "ja";

const en = {
  nav: {
    tonight: "Tonight",
    trackRecord: "Track record",
    modelLab: "Compare models",
    teams: "Teams",
    teamsTrends: "Stat trends",
    scatter: "Stat scatter",
    players: "Players",
    playersProjections: "Player projections",
    playersDeepDive: "Player deep-dive",
    advisor: "Fantasy advisor",
    drivers: "What wins games",
    about: "About",
  },

  footer: {
    disclaimer: "Predictions are machine-learning model output, not betting advice.",
    privacy: "Privacy policy",
  },

  ads: {
    // AdSense only permits "Advertisement(s)" / "Sponsored links" as labels.
    label: "Advertisement",
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
    offseasonLinkExplore: "Browse team stats →",
    latestSlate: (date: string) => `Latest slate — ${date}`,
    predictionsFor: (date: string) => `Predictions for ${date}`,
    staleNote: "Tonight's predictions aren't posted yet (or there are no games today) — this is the most recent slate the models predicted.",
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
    pick: "Models' pick",
    market: "Market",
    final: "Final",
    coinFlip: "coin flip",
    pickEm: "pick'em",
    agree: (n: number, total: number) => `${n} of ${total} models agree`,
    pickTitle: (team: string, pct: number) =>
      `${team} at ${pct}%: the average of the models' win probabilities`,
    modelTitle: (winner: string, pct: number) => `${winner} at ${pct}% win probability`,
    modelMargin: (team: string, n: string) => `${team} by ${n}`,
    modelWin: (team: string, pct: number) => `${team} ${pct}%`,
    split: "split",
    splitTitle: (marginTeam: string, winner: string, pct: number) =>
      `Split signal: this model's margin favors ${marginTeam}, but its win-probability head gives ${winner} ${pct}%. The pick column and the "models agree" count use the win probability.`,
    marketTitle: (line: string) =>
      `Betting-market line: ${line}. The latest pre-game line, which becomes the closing line at tip-off.`,
    noLine: "No market line captured for this game yet",
    pickRight: "The models' pick won",
    pickWrong: "The models' pick lost",
    caption:
      'One row per game. "Models\' pick" is the team favored by the average of the three models\' win probabilities, and how many models agree. Each model column is the margin that model expects (green if that team won, red if not), with its own win probability underneath. Margin and win probability come from two separately trained parts of each model, so they can occasionally favor different teams — flagged "split". "Market" is the betting line ("BOS -6.5" means BOS favored by 6.5), shown as a benchmark, not a pick. Hover a cell for details.',
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
    cardSpread: "Against the spread",
    cardSpreadSub: (w: number, l: number, ties: number) =>
      `${w}–${l}${ties > 0 ? `–${ties}` : ""} — the model's own margin as its line, graded against the final score: a win when its team wins by more than the stated number`,
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
    cdfTitle: "Share of games within N points",
    cdfXLabel: "Margin miss (pts)",
    cdfYLabel: "Share of games",
    cdfTick: (x: number) => `≤${x}`,
    cdfCaption:
      "The same misses as above, read as a running total instead of a weekly average: each point is the share of games whose predicted margin landed within that many points of the real result. Higher and further left is better — and unlike the chart above, there is no week-to-week noise. Every series counts only games with a closing line, so the dashed market benchmark is on the same footing.",
    predVsActual: "Predicted vs actual margin",
    scatterCaption:
      "One point per game (home-team perspective). On the dashed diagonal the predicted margin was exact; any point on a tinted field is a missed winner call — notice how the misses crowd the middle, games the model itself saw as close. The solid orange line is the least-squares fit through every point: the closer it hugs the diagonal, the less bias in the margin predictions.",
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
    confTitle: "Hit rate by pick confidence",
    confXLabel: "Pick confidence",
    confCaption:
      "Confidence is the probability the model gave its own pick. Each bar is the hit rate of picks in that band; a band needs at least 20 graded picks to draw a bar (game counts in the tooltip). A well-behaved model climbs from left to right — its surer picks should land more often. The dashed line is coin-flip.",
    agreeTitle: "When the models agree — and when they don't",
    agree: {
      consensus: "All three agree",
      majority: "2–1 majority pick",
      dissenter: "Lone dissenter",
    } as Record<string, string>,
    agreeCaption:
      "Only games where all three models logged a graded pick. When they all agree, the shared pick is scored once; on 2–1 splits, the two-model majority and the lone dissenter are scored separately. Game counts in the tooltip; the dashed line is coin-flip.",
    skillTitle: "Skill curve — wins above coin-flip",
    skillYLabel: "Wins above coin-flip",
    skillCaption:
      "The running total of correct picks minus half the games played: a coin-flipper drifts around zero, skill climbs. Every series counts only games with a market closing line, so the dashed market-favorite benchmark is on the same footing.",
    histTitle: "Margin miss distribution",
    histXLabel: "Predicted − actual home margin (pts)",
    histCaption:
      "Signed margin miss for every graded game, in 5-point bins (the outermost bars collect all larger misses). Centered on zero means unbiased; a hump to the right of zero means the model systematically overrates the home side. This is the spread behind the single margin-miss number.",
    nGames: (n: number) => `${n.toLocaleString()} games`,
    calibration: "Calibration — predicted win prob vs. actual home-win rate",
    calibXLabel: "Predicted home win %",
    roc: "ROC — how cleanly each model separates home wins from losses",
    rocCaption:
      'How to read: each point along a curve is a different confidence cutoff for calling "home win." The higher a curve bows above the dashed diagonal (coin-flip), the better that model ranks games — AUC 0.5 is no skill, 1.0 is perfect. Unlike accuracy, this scores the probabilities, not just the picks.',
    confusion: "Confusion matrix — where the misses live",
    confusionCaption:
      "How to read: rows are what actually happened, columns are what the model picked. The two green diagonal cells are correct calls; off-diagonal are mistakes. TN = correctly called an away win, TP = correctly called a home win, FP = picked home but away won, FN = picked away but home won. Comparing FP vs FN shows whether a model leans too hard on home court. The market matrix counts each game once, its pick being the closing-line favorite; games with a pick'em line (no favorite) are excluded.",
    gameByGame: "Game-by-game results",
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
    cellTitle: (winner: string, pct: number, coin: boolean, margin: string) =>
      `${winner} at ${pct}% win probability${coin ? " (coin flip)" : ""} · projected margin: ${margin}`,
    cellPick: (team: string, margin: string) => `${team} by ${margin}`,
    gradeLabel: "Grade:",
    modeSu: "Winner classification",
    modeAts: "Against the spread",
    market: "Market",
    marketTitle: (line: string) => `the market's closing line: ${line}`,
    cellTitleAts: (team: string, num: string) =>
      `graded against the final score only: correct if ${team} wins by more than ${num}`,
    noCallTitle: "The model's margin is exactly zero — no side to grade",
    pushTitle: "The final margin landed exactly on the stated number — no winner",
    captionSu:
      'Winner classification: cells show each predictor\'s call — the market\'s closing favorite and each model\'s pick — green when that team won, red when it didn\'t. Newest games first; scroll within the table; hover a model\'s cell for its win probability and projected margin. "—" means no closing line, or no prediction for the game.',
    captionAts:
      'Against the spread: each cell is that predictor\'s own line — "SAS -6.5" from the market means SAS favored by 6.5; "SAS -1.7" from a model means it expects SAS to win by 1.7. Every line is graded against the final score alone: green if the stated team won by more than its number, red if not, gray if the game landed exactly on it (a push). Models are graded against their own numbers, not the market\'s.',
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

  advisor: {
    title: "Fantasy advisor",
    subtitle:
      "Ask lineup, start/sit, streaming, waiver, trade, or keeper questions — answers are grounded in season stats plus the same projections shown on the",
    tableLink: "daily table.",
    promptLabel: "Your question",
    promptPlaceholder: "e.g. Who should I start at guard tonight? Or: is this trade offer worth taking?",
    rosterLabel: "Your roster (optional)",
    rosterPlaceholder: "Paste your roster, one player per line.",
    matchupLabel: "Matchup score (optional):",
    matchupPlaceholder: "e.g. up 12 pts / down 2 cats",
    scoringLabel: "Scoring:",
    scoringPoints: "Points league",
    scoringCategory: "Category league",
    submit: "Get advice",
    thinking: "Thinking…",
    errLoad: (e: string) => `Couldn't get advice: ${e}`,
    answerHeading: (d: string | null) =>
      d ? `Advice (projection slate: ${d})` : "Advice (based on season stats — no games in the current window)",
    disclaimer:
      "Advice is generated by an AI model from HoopModel's statistical projections and season stats. It can be wrong; it is not betting advice. Questions you submit and the answers generated may be stored to improve the service — please don't include personal information.",
  },

  playersDaily: {
    title: "Player projections",
    subtitle:
      "Every rotation player's projected counting stats for one day's slate, next to the pace and defense context behind them. Click a column header to sort.",
    exploreLink: "Deep-dive a single player →",
    dateLabel: "Date:",
    teamLabel: "Team:",
    allTeams: "All teams",
    modeLabel: "Values",
    modePred: "Predicted",
    modeActual: "Actual",
    errLoad: (e: string) => `Couldn't load: ${e}`,
    loading: "Loading…",
    noData: "No player projections yet — they publish nightly during the season.",
    noRows: "No rows for this date/team.",
    tableHeading: (d: string, n: number) => `${d} — ${n} players`,
    gradedNote:
      "This slate is final: toggle between what the model predicted pregame and what actually happened.",
    upcomingNote: "Projections are computed pregame from each player's recent form.",
    contextNote:
      "Context columns are rolling last-10-game values as of the game date: possessions per 48 (pace), opponent points allowed per 100 possessions (DRtg), and opponent three-point attempts conceded per game.",
    playerCol: "Player",
    matchupCol: "Matchup",
    ctxCols: {
      team_pace_l10: "Team pace",
      opp_pace_l10: "Opp pace",
      opp_drtg_l10: "Opp DRtg",
      opp_3pa_allowed_l10: "Opp 3PA allowed",
    } as Record<string, string>,
  },

  playersExplore: {
    title: "Player explorer",
    subtitle:
      "Per-game counting stats for every rotation player, next to what our projection model predicted for that game. Pick a team, a player, a stat, and a window.",
    dailyLink: "← Back to the daily projections table",
    teamLabel: "Team:",
    playerLabel: "Player:",
    statLabel: "Stat:",
    windowLabel: "Window:",
    windows: {
      L5: "Last 5 games",
      L10: "Last 10 games",
      season: "This season",
      three: "Last 3 seasons",
    } as Record<string, string>,
    errLoad: (e: string) => `Couldn't load: ${e}`,
    loading: "Loading…",
    noData: "No player projections available yet.",
    noPreds:
      "No model predictions in this window — projections cover the 2023-24 season onward.",
    chartHeading: (name: string, stat: string) => `${name} — ${stat}, game by game`,
    backtestNote:
      "Predicted values are the model's out-of-sample backtest: each one was produced by a model trained only on earlier seasons.",
    lineTitle: (stat: string) => `Clearing a line — ${stat}`,
    lineLabel: "Line:",
    tileGames: "Games",
    tileAvg: "Average",
    tileSd: "Std dev",
    perGame: "per game",
    sdSub: "spread around the average",
    tileOver: (line: string) => `Over ${line}`,
    overSub: (k: number, n: number, lo: string, hi: string) =>
      `${k} of ${n} games · 95% CI ${lo}–${hi}%`,
    tileModel: "Model-implied",
    modelSub: "from the model's Poisson rate for this window",
    curveXLabel: "Line",
    curveYLabel: "Share of games over",
    lineCaption:
      "The curve is the whole story at once: for every possible line, the share of games in the selected window that beat it. Click anywhere on the curve — or edit the line box — to move the orange marker; the tiles recompute as it moves. The confidence interval says how far a rate from this few games can be trusted; over 5 games it is wide by construction. For streaky low-count stats the model-implied tile shows the probability the model's own Poisson rate assigns to clearing the line. These are descriptive statistics about past games, not betting advice.",
    tipProj: (v: string) => `(proj ${v})`,
    distHeading: (stat: string) => `${stat} distribution`,
    distPoissonNote:
      "The dotted line is the frequency the model's Poisson rate implies — bars far from the line mean the model mis-judges how streaky this stat is.",
    errHeading: (stat: string) => `Prediction error (predicted − actual ${stat})`,
    errSummary: (n: number, mae: number, bias: number) =>
      `${n} predicted games · average miss ${mae.toFixed(2)} · bias ${bias >= 0 ? "+" : ""}${bias.toFixed(2)} (positive = model too high).`,
    shareOfGames: "Share of games",
    poissonExpected: "Model-implied share",
    predicted: "Predicted",
    actual: "Actual",
    teamCompareHeading: "Team vs next opponent (last 10 games)",
    nextGame: (date: string, isHome: boolean, opp: string) =>
      `Next game: ${date} ${isHome ? "vs." : "@"} ${opp}`,
    noNextGame: "No upcoming game scheduled (offseason) — showing the team profile alone.",
    statCol: "Stat",
    teamCol: "Team",
    oppCol: "Opponent",
    rowLabels: {
      pace: "Pace",
      off_rtg: "Off. rating",
      def_rtg: "Def. rating",
      efg_pct: "eFG%",
      oreb_pct: "OREB%",
      dreb_pct: "DREB%",
      ast_pct: "AST%",
      fg3a_pg: "3PA / game",
      fta_pg: "FTA / game",
      pts_pg: "PTS / game",
    } as Record<string, string>,
    compareCaption:
      "Rolling averages over each team's last 10 games. Pace and opponent defense are the context the projections lean on most.",
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
    title: "Team stats",
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
    quadAwayPick: "picked away · home won",
    quadHomePick: "picked home · away won",
    picked: (pick: string) => `picked ${pick}`,
    predActual: (x: string, y: string) => `predicted ${x} · actual ${y}`,
    noGraded: "No graded games in this window yet.",
  },
};

export type Dict = typeof en;

const ja: Dict = {
  nav: {
    tonight: "本日の試合の予測",
    trackRecord: "予測モデルの実績",
    modelLab: "予測モデルを比較",
    teams: "チーム成績",
    teamsTrends: "トレンド",
    scatter: "スタッツの可視化ツール",
    players: "選手成績",
    playersProjections: "本日の成績予測",
    playersDeepDive: "選手の詳細分析",
    advisor: "ファンタジー・バスケ相談所",
    drivers: "勝敗の分かれ目",
    about: "このサイトについて",
  },

  footer: {
    disclaimer:
      "本サイトの予測は機械学習モデルの出力であり、賭けを推奨するものではありません。",
    privacy: "プライバシーポリシー",
  },

  ads: {
    label: "広告",
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
    actualHomeWinRateY: "実際のホーム勝率",
    rocNotEnough: "ROC曲線を描くには、採点済みの試合がまだ足りません。",
    rocXLabel: "偽陽性率（ホーム勝ちと予測して外れた割合）",
    rocYLabel: "真陽性率",
    corrXLabel: "最終点差との相関係数",
  },

  home: {
    heroTitle: "NBAの全試合を、毎日予測。",
    heroSub:
      "3つの機械学習モデルがNBAの全試合の勝敗を予測します。予測はすべて試合前に記録され、実際の結果と照らし合わせて採点したうえで、当たりも外れもそのまま当サイトに掲載しております。",
    ctaTonight: "本日の試合の予測を見る",
    ctaRecord: "これまでの成績を見る",
    windowLast30: "直近30日",
    windowLastSeason: "昨シーズン",
    proofWinners: (window: string) => `勝敗的中率（${window}）`,
    proofMarginLine1: "平均点差誤差",
    proofLoggedLine1: "これまでの予測数",
    proofLoggedLine2: "（全件を公開・採点）",
    errLoad: (e: string) => `予測を読み込めませんでした: ${e}`,
    loading: "予測を読み込んでいます…",
    offseasonTitle: "今はオフシーズンです",
    offseasonBody:
      "試合の予測は、10月のシーズン開幕とともに再開します。オフシーズン中も、これまでのすべての予測と採点結果は引き続き公開しています。",
    offseasonLinkRecord: "昨シーズンの成績を見る →",
    offseasonLinkExplore: "チーム統計を見てみる →",
    latestSlate: (date: string) => `直近の予測 — ${date}`,
    predictionsFor: (date: string) => `${date}の予測`,
    staleNote: "本日の予測はまだ掲載されていないか、本日は試合がありません。直近に予測した試合を表示しています。",
    howTitle: "予測のしくみ",
    step1Title: "データ収集",
    step1Body:
      "得点やリバウンドなどの基本スタッツをはじめ、ハッスル・選手トラッキング系の指標を全試合から取り込みます。",
    step2Title: "直近の調子を数値化",
    step2Body: "各チームの最近の戦いぶりを、特徴量として数値化します。",
    step3Title: "3つのモデルが予測",
    step3Body:
      "ランダムフォレスト、勾配ブースティング、ニューラルネットが、各試合の勝者と点差を予測します。",
    step4Title: "結果を公開採点",
    step4Body: "予測は試合前に掲載され、実際の最終スコアと照らし合わせて採点します。",
    step4Link: "全記録を見る →",
    longerVersion: "機械学習モデルやデータ処理の流れをもっと詳しく知りたい方は:",
    howLink: "HoopModelのしくみ →",
  },

  predTable: {
    matchup: "対戦カード",
    pick: "モデルの予測",
    market: "市場",
    final: "最終スコア",
    coinFlip: "五分五分",
    pickEm: "互角",
    agree: (n: number, total: number) => `${total}モデル中${n}モデルが支持`,
    pickTitle: (team: string, pct: number) =>
      `${team}の勝つ確率は${pct}%（各モデルの予測勝率の平均）`,
    modelTitle: (winner: string, pct: number) => `${winner}の勝つ確率: ${pct}%`,
    modelMargin: (team: string, n: string) => `${team} ${n}点差`,
    modelWin: (team: string, pct: number) => `${team} ${pct}%`,
    split: "判断が分かれる",
    splitTitle: (marginTeam: string, winner: string, pct: number) =>
      `このモデル内で判断が分かれています。点差では${marginTeam}が優勢ですが、勝率では${winner}が${pct}%です。「モデルの予測」列と支持モデル数は勝率をもとにしています。`,
    marketTitle: (line: string) =>
      `市場の予想点差: ${line}（試合前の最新値。ティップオフ時点の値が最終予想点差になります）`,
    noLine: "この試合の市場予想点差はまだ取得していません",
    pickRight: "モデルの予測が的中",
    pickWrong: "モデルの予測が外れ",
    caption:
      "1試合を1行にまとめています。「モデルの予測」は、3つのモデルが出した勝率の平均で優勢なチームと、そのチームを支持するモデルの数です。各モデルの列はそのモデルが予想する点差（そのチームが勝てば緑、負ければ赤）と、その下にそのモデル自身の勝率を表示しています。点差と勝率はモデル内の別々の仕組みで算出するため、まれに優勢なチームが食い違うことがあり、その場合は「判断が分かれる」と表示します。「市場」はベッティング市場の予想点差（「BOS -6.5」はBOSが6.5点差で優勢という意味）で、予想ではなく比較の基準として掲載しています。各セルにカーソルを合わせると詳細が表示されます。",
  },

  injury: {
    title: (date: string) => `出場可否状況 — ${date}`,
    subtitle:
      "試合前にNBAが公表する公式の負傷者リストです。選手の出場可否はモデルにも入力され、予測に反映されます。",
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
      "すべての予測を試合前に記録し、試合終了後に採点しています。このページはその全成績表です。あとからの修正は一切ありません。",
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
    noGraded: "この期間には、採点済みの試合がまだございません。",
    cardWinnerAcc: "勝敗的中率",
    cardWinnerSub: (model: string) => `${model}`,
    cardMarginMiss: "平均点差誤差",
    cardMarginSub: "予測した点差と実際の得失点差のずれ",
    cardMarket: "市場による予測得失点差",
    cardMarketSub: (modelMae: string, n: string, total: string, closerPct: number) =>
      `当モデルは±${modelMae}。市場による予測得失点差がある${n}試合（採点済み${total}試合中）で比較すると、${closerPct}%の試合で当モデルの方が実際の点差に近い予測でした`,
    cardSpread: "予測点差込みの勝敗（ATS）",
    cardSpreadSub: (w: number, l: number, ties: number) =>
      `${w}勝${l}敗${ties > 0 ? `${ties}分` : ""} — モデル自身の予測点差を基準に最終スコアで採点し、示したチームがその点差より大きく勝てば的中です`,
    cardGraded: "採点済みの試合",
    cardGradedSub: "この期間の合計",
    marketSeries: "市場による最終予測点差",
    clsTitle: "勝敗的中率 — 市場とモデルの比較",
    clsCaption:
      "公平に比較するため、市場の最終予測点差データが存在する採点済みの試合だけで集計しています。市場の「予測」は本命(有利と見られた側)です。どちらが有利とも言えない互角の試合は、予測なしとして除外されます。バーをタップすると試合数が表示されます。",
    marketFavorite: "市場の本命",
    recentPicks: (model: string) => `直近の予測 — ${model}`,
    picksCaption: (n: number) =>
      `直近${n}件の採点済み予測です(左から古い順)。マスをタップすると試合の詳細が表示されます。`,
    accOverTime: "勝敗的中率の推移",
    accCaption:
      "各点は、その日までの7日間の成績を示します。薄い破線は同じ試合における市場の本命の的中率。",
    maeOverTime: "点差誤差の推移",
    maeCaption:
      "その日までの7日間で、予測が実際の点差から平均何点ずれていたかを示します(小さいほど優秀です)。破線は同じ試合に対してブックメーカーが試合直前に示した最終予測点差で、点差予測の基準としては最も厳しい公開ベンチマークです。自己評価のために掲載しているもので、予測の宣伝が目的ではありません。",
    cdfTitle: "誤差N点以内に収まった試合の割合",
    cdfXLabel: "点差の誤差（点）",
    cdfYLabel: "試合の割合",
    cdfTick: (x: number) => `≤${x}`,
    cdfCaption:
      "上のグラフと同じ誤差を、週ごとの平均ではなく累計で読み直したものです。各点は、予測点差と実際の点差のずれがその点数以内に収まった試合の割合を表します。線が左上に寄っているほど正確で、週ごとのぶれに左右されません。すべての系列は市場の最終予測点差がある試合だけを対象にしているため、破線のベンチマークと同じ土俵で比較できます。",
    predVsActual: "予測点差と実際の点差",
    scatterCaption:
      "1つの点が1試合を表します(ホームチーム視点)。破線の対角線上にある点は点差まで的中した予測で、色の付いた領域にある点は勝敗を外した試合です。外れがグラフ中央――モデル自身が接戦と見ていた試合――に集中していることが見て取れます。オレンジの実線は全試合に対する回帰直線で、対角線に近いほど点差予測に偏りがないことを示します。",
    homeAway: "ホーム予測とアウェイ予測",
    pickHome: "ホーム勝利と予測したとき",
    pickAway: "アウェイ勝利と予測したとき",
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
    noCompleted: "この期間には、終了した試合がまだございません。",
    accuracyGames: (n: number) => `的中率（${n}試合）`,
    maeCalib: (mae: string, calib: string) => `平均誤差 ${mae}点 · 較正誤差 ${calib}`,
    confTitle: "確信度別の的中率",
    confXLabel: "予測の確信度",
    confCaption:
      "確信度は、モデルが自分の選んだ側に与えた勝率です。棒は、その確信度帯に入る予測が実際に的中した割合を示します（採点済みが20試合に満たない帯は表示しません。試合数はカーソルで確認できます）。健全なモデルほどグラフは右肩上がりになり、確信の強い予測ほどよく当たるはずです。破線はコイン投げと同じ50%です。",
    agreeTitle: "3つのモデルの予測が一致するとき・割れるとき",
    agree: {
      consensus: "3モデル一致",
      majority: "2対1の多数派",
      dissenter: "少数派の1モデル",
    } as Record<string, string>,
    agreeCaption:
      "3つのモデルすべてが予測し、採点済みの試合が対象です。予測が一致した試合では共通の予測を、2対1に割れた試合では多数派（2モデル）と少数派（1モデル）を分けて採点しています。試合数はカーソルで確認できます。破線は50%です。",
    skillTitle: "スキルカーブ — コイン投げを上回る的中数",
    skillYLabel: "コイン投げ超過の的中数",
    skillCaption:
      "（的中数 − 試合数の半分）の累計です。コイン投げなら0付近を漂い、実力があれば右肩上がりになります。すべての系列は市場の最終予測点差がある試合だけを対象にしているため、破線で示した市場のコンセンサス（本命）と同じ土俵で比較できます。",
    histTitle: "点差誤差の分布",
    histXLabel: "予測点差 − 実際の点差（点）",
    histCaption:
      "採点済みの全試合について、予測点差と実際の点差のずれ（符号付き）を5点刻みで集計しています（両端の棒は±30点を超える誤差をまとめたものです）。0を中心に対称なら偏りがなく、0より右に山が寄っていればホーム側を過大評価している傾向です。平均誤差という1つの数字には表れない、誤差の広がりが見えます。",
    nGames: (n: number) => `${n.toLocaleString()}試合`,
    calibration: "キャリブレーション — 予測勝率どおりに勝っているか",
    calibXLabel: "予測ホーム勝率（%）",
    roc: "ROC曲線 — ホームの勝ち負けをどこまで見分けられるか",
    rocCaption:
      "見方: 曲線上の各点は、どこまで確信があれば「ホーム勝利」と判定するか、そのしきい値を変えたときの結果に対応します。曲線が破線の対角線(コイン投げと同等)より上に膨らむほど、そのモデルは勝敗の見極めに優れています。AUCは0.5で予測力なし、1.0で完全な予測です。的中率と異なり、予測の当たり外れではなく、出力された確率そのものを評価する指標です。",
    confusion: "混同行列 — どんな外し方をしているか",
    confusionCaption:
      "見方: 行が実際の結果、列がモデルの予測です。対角線上の緑の2マスが正解、残りの2マスが不正解です。TNはアウェイ勝利の的中、TPはホーム勝利の的中、FPはホーム勝利と予測して外れた試合、FNはアウェイ勝利と予測して外れた試合を表します。FPとFNを比較すると、モデルがホーム側に偏っていないかを確認できます。市場の行列は各試合を1回だけ集計し、市場の最終予測点差で優勢とされた側をその予測として扱います。どちらが有利とも言えない互角の試合は除外しています。",
    gameByGame: "試合ごとの結果",
  },

  confMatrix: {
    pickedAway: "アウェイと予測",
    pickedHome: "ホームと予測",
    awayWon: "アウェイが勝利",
    homeWon: "ホームが勝利",
  },

  resultsTable: {
    date: "日付",
    matchup: "対戦カード",
    final: "最終スコア",
    cellTitle: (winner: string, pct: number, coin: boolean, margin: string) =>
      `${winner}が勝つ確率 ${pct}%${coin ? "（五分五分）" : ""} ・ 予測点差: ${margin}`,
    cellPick: (team: string, margin: string) => `${team} ${margin}点差`,
    gradeLabel: "採点基準:",
    modeSu: "勝敗の分類",
    modeAts: "点差込みの採点（ATS）",
    market: "市場",
    marketTitle: (line: string) => `市場の最終予測点差: ${line}`,
    cellTitleAts: (team: string, num: string) =>
      `最終スコアのみで採点: ${team}が${num}点差より大きく勝てば的中`,
    noCallTitle: "モデルの予測点差が0のため、採点対象外です",
    pushTitle: "実際の点差が示された数字とちょうど同じだった試合（勝敗なし）",
    captionSu:
      "勝敗の分類: 各欄には市場（最終予測点差で優勢とされた側）と各モデルの予測勝者を表示し、そのチームが勝てば緑、負ければ赤になります。新しい試合が上で、表内をスクロールできます。モデルの欄にカーソルを合わせると勝率と予測点差が表示されます。「—」は市場の予測点差がない、または予測がない試合です。",
    captionAts:
      "点差込みの採点: 各欄にはその予測者自身の予測点差を表示します。市場の「SAS -6.5」はSASが6.5点差で優勢という意味で、モデルの「SAS -1.7」はSASが1.7点差で勝つという予測です。採点は最終スコアだけと比較して行います。示されたチームがその数字より大きい点差で勝てば緑、そうでなければ赤、ちょうどその点差なら灰色（引き分け扱い）です。モデルは市場の数字ではなく、自分自身の点差に対して採点されます。",
  },

  picksStrip: {
    aria: (n: number) => `直近${n}件の採点済み予測`,
    chipTitle: (date: string, away: string, home: string, pick: string) =>
      `${date} ${away} @ ${home}｜予測は${pick}`,
    detailPicked: "予測は",
    detailFinal: (score: string) => ` · 最終スコア ${score}`,
    detailWon: (winner: string) => ` · ${winner}が勝利`,
    hit: "的中",
    miss: "外れ",
  },

  advisor: {
    title: "ファンタジー・バスケ相談所",
    subtitle:
      "スタメンの決定や選手の入れ替え、ストリーミング、ウェイバー補強、トレードやキーパーの判断といった質問にAIが回答します。根拠はシーズン実績と成績予測。予測はこちら:",
    tableLink: "日別予測の一覧",
    promptLabel: "質問",
    promptPlaceholder:
      "例: 今夜ガードで先発させるべきなのは? このトレード提案、受けるべき?",
    rosterLabel: "ロスター（任意）",
    rosterPlaceholder: "ロスターを1行に1人ずつ貼り付けてください。",
    matchupLabel: "対戦スコア（任意）:",
    matchupPlaceholder: "例: 12ポイントリード / 2カテゴリービハインド",
    scoringLabel: "リーグ形式:",
    scoringPoints: "ポイントリーグ",
    scoringCategory: "カテゴリーリーグ",
    submit: "相談する",
    thinking: "考えています…",
    errLoad: (e: string) => `回答を取得できませんでした: ${e}`,
    answerHeading: (d: string | null) =>
      d ? `回答（${d}の成績予測に基づく）` : "回答（シーズン実績に基づく・現在は試合のない期間です）",
    disclaimer:
      "回答は、HoopModelの統計的な成績予測とシーズン実績をもとにAIモデルが生成しています。内容が誤っている可能性があり、賭けを推奨するものでもありません。送信された質問と生成された回答はサービス改善のために保存されることがあります。個人情報は入力しないでください。",
  },

  playersDaily: {
    title: "選手の成績予測",
    subtitle:
      "その日の全試合について、ローテーション選手の主要スタッツの予測を、根拠となるペースや守備の状況とあわせて一覧にしています。列の見出しをクリックすると並べ替えられます。",
    exploreLink: "選手ごとの詳細を見る →",
    dateLabel: "日付:",
    teamLabel: "チーム:",
    allTeams: "全チーム",
    modeLabel: "表示する値",
    modePred: "予測値",
    modeActual: "実際の値",
    errLoad: (e: string) => `読み込めませんでした: ${e}`,
    loading: "読み込んでいます…",
    noData: "選手の成績予測はまだございません。シーズン中は毎晩更新されます。",
    noRows: "この日付・チームに該当する選手がいません。",
    tableHeading: (d: string, n: number) => `${d} — ${n}人`,
    gradedNote:
      "この日の試合はすべて終了しています。試合前の予測値と実際の値を切り替えて確認できます。",
    upcomingNote: "予測値は、各選手の直近の調子をもとに試合前に算出しています。",
    contextNote:
      "状況の列は、試合日時点の直近10試合平均です。ペースは48分あたりのポゼッション数、相手DRtgは対戦相手の守備が100ポゼッションあたりに許す失点、相手被3PAは対戦相手が1試合に許す3ポイント試投数を表します。",
    playerCol: "選手",
    matchupCol: "対戦",
    ctxCols: {
      team_pace_l10: "チームペース",
      opp_pace_l10: "相手ペース",
      opp_drtg_l10: "相手DRtg",
      opp_3pa_allowed_l10: "相手被3PA",
    } as Record<string, string>,
  },

  playersExplore: {
    title: "選手の詳細分析",
    subtitle:
      "ローテーション選手の試合ごとのスタッツを、モデルが試合前に出した予測値と並べて表示します。チーム、選手、スタッツ、期間を選んでください。",
    dailyLink: "← 日別予測の一覧に戻る",
    teamLabel: "チーム:",
    playerLabel: "選手:",
    statLabel: "スタッツ:",
    windowLabel: "期間:",
    windows: {
      L5: "直近5試合",
      L10: "直近10試合",
      season: "今シーズン",
      three: "過去3シーズン",
    } as Record<string, string>,
    errLoad: (e: string) => `読み込めませんでした: ${e}`,
    loading: "読み込んでいます…",
    noData: "選手の成績予測はまだございません。",
    noPreds: "この期間にはモデルの予測値がございません。予測の対象は2023-24シーズン以降です。",
    chartHeading: (name: string, stat: string) => `${name} — ${stat}の推移（試合ごと）`,
    backtestNote:
      "予測値はバックテストによるもので、いずれも対象シーズンより前のデータだけで学習したモデルの出力です。結果を知った上での後づけ予測ではありません。",
    lineTitle: (stat: string) => `基準値超えの割合 — ${stat}`,
    lineLabel: "基準値:",
    tileGames: "試合数",
    tileAvg: "平均",
    tileSd: "標準偏差",
    perGame: "1試合あたり",
    sdSub: "平均まわりのばらつき",
    tileOver: (line: string) => `${line}超え`,
    overSub: (k: number, n: number, lo: string, hi: string) =>
      `${n}試合中${k}試合 · 95%信頼区間 ${lo}–${hi}%`,
    tileModel: "モデル推定",
    modelSub: "この期間のポアソン率から計算した確率",
    curveXLabel: "基準値",
    curveYLabel: "基準値を超えた試合の割合",
    lineCaption:
      "この曲線は、あらゆる基準値に対して「選択中の期間で何%の試合がそれを上回ったか」を一望できるものです。曲線上をクリックするか基準値の入力欄を変更すると、オレンジのマーカーが動き、下のタイルも連動して再計算されます。信頼区間は、この試合数から出した割合がどこまであてになるかの目安で、直近5試合のような短い期間では必然的に広くなります。ムラの大きい少数カウント系のスタッツでは、モデル自身のポアソン率が基準値超えに割り当てる確率も併記しています。いずれも過去の試合に関する記述統計であり、賭けを推奨するものではありません。",
    tipProj: (v: string) => `（予測 ${v}）`,
    distHeading: (stat: string) => `${stat}の分布`,
    distPoissonNote:
      "点線は、モデルのポアソン分布が示す理論上の頻度です。棒が点線から大きく離れている場合、このスタッツのムラをモデルがうまく捉えられていないことを意味します。",
    errHeading: (stat: string) => `予測誤差（予測値 − 実際の${stat}）`,
    errSummary: (n: number, mae: number, bias: number) =>
      `予測対象${n}試合 · 平均誤差 ${mae.toFixed(2)} · 偏り ${bias >= 0 ? "+" : ""}${bias.toFixed(2)}（正の値はモデルの過大評価）`,
    shareOfGames: "試合の割合",
    poissonExpected: "モデルの理論値",
    predicted: "予測",
    actual: "実際",
    teamCompareHeading: "チームと次の対戦相手の比較（直近10試合）",
    nextGame: (date: string, isHome: boolean, opp: string) =>
      `次の試合: ${date} ${isHome ? "vs." : "@"} ${opp}`,
    noNextGame: "予定されている試合はございません（オフシーズン）。チームの数値のみ表示しています。",
    statCol: "スタッツ",
    teamCol: "チーム",
    oppCol: "相手",
    rowLabels: {
      pace: "ペース",
      off_rtg: "攻撃効率（ORtg）",
      def_rtg: "守備効率（DRtg）",
      efg_pct: "eFG%",
      oreb_pct: "OREB%",
      dreb_pct: "DREB%",
      ast_pct: "AST%",
      fg3a_pg: "3PA/試合",
      fta_pg: "FTA/試合",
      pts_pg: "PTS/試合",
    } as Record<string, string>,
    compareCaption:
      "各チームの直近10試合の平均です。成績予測が特に重視しているのは、ペースと相手の守備です。",
  },

  drivers: {
    title: "勝敗の分かれ目",
    subtitle:
      "直近数試合の各スタッツが、試合の最終点差とどの程度相関しているかを示します。相関が正であれば、その値が高いほど勝利につながりやすいことを意味します。",
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
    noData: "相関データがまだございません。",
    strongestPos: "正の相関が最も強いのは",
    strongestNeg: "負の相関が最も強いのは",
    featureCounts: (n1: number, n2: number, total: number) =>
      `|r| > 0.1 のスタッツは${n1}件、|r| > 0.2 は${n2}件です（全${total}件中）。`,
    topHeading: (n: number) => `点差との相関が強いスタッツ（上位${n}件）`,
    noCorrelations: "相関データがまだございません。",
  },

  explore: {
    title: "チーム統計",
    subtitle:
      "スタッツをひとつ選ぶと、各チームの調子（直近5試合または10試合の移動平均）がシーズンを通してどう推移したかを確認できます。",
    statLabel: "スタッツ:",
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
    noStatData: "このスタッツのデータはまだございません。",
    rollingHeading: (feature: string, window: string) =>
      `${feature}の移動平均（${window}）`,
    chartYLabel: (feature: string, window: string) =>
      `${feature}（直近${window === "L5" ? 5 : 10}試合平均）`,
    pickTeam: "チームをひとつ以上選んでください。",
    noGamesInRange: "この期間に、選んだチームの試合はございません。",
    categories: {
      Traditional: "基本スタッツ",
      Advanced: "応用スタッツ",
      "Four Factors": "フォーファクター",
      Hustle: "ハッスル",
      Tracking: "トラッキング",
      Misc: "その他",
      Scoring: "得点内訳",
    } as Record<string, string>,
  },

  scatter: {
    title: "スタッツの散布図",
    subtitle:
      "1チームの1試合がひとつの点になります。スタッツを2つ選ぶと勝敗別に色分けして表示され、回帰直線の表示や、チームによる絞り込みもできます。",
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
      "チームを選ぶと、縦軸・横軸それぞれに沿って、そのチームの勝ち試合（緑）と負け試合（赤）のスタッツの分布を箱ひげ図で表示します。箱にカーソルを合わせると最小値・四分位数・中央値を確認できます。",
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
    xLabel: "ホーム側の予測得失点差（点）",
    yLabel: "ホーム側の実際の得失点差（点）",
    winnerCalled: "勝者を的中",
    missed: "外れ",
    quadAwayPick: "予測はアウェイ · 勝者はホーム",
    quadHomePick: "予測はホーム · 勝者はアウェイ",
    picked: (pick: string) => `予測は${pick}`,
    predActual: (x: string, y: string) => `予測 ${x} · 実際 ${y}`,
    noGraded: "この期間には、採点済みの試合がまだございません。",
  },
};

export const translations: Record<Lang, Dict> = { en, ja };
