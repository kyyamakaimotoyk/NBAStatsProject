// Long-form "how to read this page" guides, one per data page, rendered by
// <PageGuide/> at the bottom of the page. Kept out of translations.ts because
// these are essays, not UI strings. Same rules as the rest of the site: the
// Japanese is a transcreation (see the glossary at the top of translations.ts),
// not a sentence-by-sentence translation. Keep both versions evergreen — no
// numbers that go stale between builds.

import type { Lang } from "./translations";

type Guide = {
  title: string;
  sections: { heading: string; body: string[] }[];
};

export type GuideKey =
  | "accuracy"
  | "performance"
  | "explore"
  | "scatter"
  | "players"
  | "playerExplore"
  | "advisor"
  | "drivers";

export const pageGuides: Record<GuideKey, Record<Lang, Guide>> = {
  accuracy: {
    en: {
      title: "How to read the track record",
      sections: [
        {
          heading: "What gets graded",
          body: [
            "Every prediction on HoopModel is written to the database before the game tips off. Once the final score is in, a nightly job grades it: did the model pick the right winner, and how far was its predicted margin from the real one? Nothing is removed or re-scored afterwards, so the misses stay on the page next to the hits.",
            "Winner accuracy is the share of games where the model's favored team won. For context, simply picking the home team every night wins a little more than half the time, so the useful question is how far above that line a model sits, and whether it stays there over a full season.",
          ],
        },
        {
          heading: "Why the betting market is on the page",
          body: [
            "The closing line from the betting market is the toughest public benchmark there is for an NBA game: it's the final consensus of a very large, very motivated crowd. We put it next to our numbers to keep ourselves honest. Beating it consistently is extremely hard, and falling a little short of it is normal for any public model.",
            "The market comparison only uses games that have a recorded closing line, so both sides are graded on exactly the same set of games. We show the line for completed games only and don't publish picks against it.",
          ],
        },
        {
          heading: "Reading the charts",
          body: [
            "The trend charts use a trailing seven-day window, so a single bad night moves them less than it would a daily number. The scatter plot shows every game as one point: the closer the cloud sits to the diagonal, the better the margins. The game-by-game table at the bottom is the raw record that every other number on this page is computed from.",
          ],
        },
      ],
    },
    ja: {
      title: "予測モデルの実績の見方",
      sections: [
        {
          heading: "採点の対象",
          body: [
            "HoopModel の予測は、すべて試合開始前にデータベースへ記録しています。試合が終わると毎晩の処理で採点し、勝者を当てたか、予測した点差が実際とどれだけずれたかを記録します。採点後に結果を消したり付け直したりはしないので、外れた予測も当たった予測と並んで残ります。",
            "勝敗的中率は、モデルが勝つと予測したチームが実際に勝った割合です。毎晩ホームチームを選ぶだけでも半分を少し上回る程度は当たるので、見るべきは「その水準をどれだけ上回るか」、そしてシーズンを通してその差を保てるかどうかです。",
          ],
        },
        {
          heading: "市場の予想点差を載せている理由",
          body: [
            "賭け市場の最終予想点差は、NBA の試合予想として公開されているなかで最も手ごわい基準です。大勢の参加者が本気で出した最終的な合意だからです。自分たちの数字を甘く見ないために、あえて並べて表示しています。これを継続して上回るのは非常に難しく、公開モデルが少し届かないのはごく普通のことです。",
            "比較には最終予想点差が記録された試合だけを使い、両者をまったく同じ試合で採点しています。表示するのは終了した試合の予想点差のみで、それに対する予想は公開していません。",
          ],
        },
        {
          heading: "グラフの読み方",
          body: [
            "推移グラフは直近7日間の移動平均なので、一晩の大きな外れに振り回されにくくなっています。散布図は1試合を1点で表し、点の集まりが対角線に近いほど点差の予測が正確だということです。いちばん下の試合ごとの表は、このページのすべての数字の元になっている生の記録です。",
          ],
        },
      ],
    },
  },

  performance: {
    en: {
      title: "How to compare the three models",
      sections: [
        {
          heading: "Three different approaches to the same question",
          body: [
            "HoopModel runs three independently trained models on every game: a random forest, a gradient-boosted tree model (XGBoost), and a neural network. All three see the same inputs, rolling team form going into the game, but they learn from it in different ways. Tree models split the data into rule-like branches; the neural network learns smooth combinations of every input at once. When they agree it tends to be for good reason, and when they split, the game is usually genuinely close.",
          ],
        },
        {
          heading: "Accuracy isn't the whole story",
          body: [
            "Two models with the same winner accuracy can still differ a lot. Calibration asks whether a 70% pick actually wins about 70% of the time; a well-calibrated model's confidence means something. The ROC curve scores the probabilities rather than the picks: it shows how cleanly a model ranks likely home wins above likely home losses at every possible cutoff.",
            "The confidence chart is the most practical view: picks the model was sure about should land more often than picks it barely made. If the bars don't climb from left to right, the model's confidence isn't telling you much.",
          ],
        },
        {
          heading: "Where the misses live",
          body: [
            "The confusion matrix splits the misses by direction. If a model has many more 'picked home, away won' errors than the reverse, it leans too hard on home-court advantage. The margin miss histogram shows the same thing for point margins: a distribution centered on zero means no systematic bias toward either side.",
          ],
        },
      ],
    },
    ja: {
      title: "3つのモデルを比べるには",
      sections: [
        {
          heading: "同じ問いへの3つの異なるアプローチ",
          body: [
            "HoopModel では、別々に学習させた3つのモデルがすべての試合を予測します。ランダムフォレスト、勾配ブースティング（XGBoost）、ニューラルネットです。入力は共通で、試合時点での各チームの直近の調子ですが、そこからの学び方が違います。決定木系のモデルはデータをルールのような枝分かれで切り分け、ニューラルネットはすべての入力をなめらかに組み合わせて学習します。3つの意見がそろうときはたいてい理由があり、割れるときは本当に拮抗した試合であることが多いです。",
          ],
        },
        {
          heading: "的中率だけでは分からないこと",
          body: [
            "勝敗的中率が同じでも、中身は大きく違うことがあります。キャリブレーションは「70%と予測した試合が、実際に7割ほど勝っているか」を確かめるもので、これが合っているモデルの確信度は信頼できます。ROC 曲線は予測の当たり外れではなく確率そのものを評価し、どの基準で線を引いてもホーム勝ちの試合を負けの試合より上位に並べられているかを示します。",
            "いちばん実用的なのは確信度別のグラフです。モデルが自信を持った予測ほどよく当たるはずで、棒が左から右へ上がっていかないなら、そのモデルの確信度はあまり当てになりません。",
          ],
        },
        {
          heading: "外れ方の傾向",
          body: [
            "混同行列は、外れた予測を方向別に分けて見せます。「ホームを選んだがアウェイが勝った」誤りが逆向きより明らかに多ければ、そのモデルはホームの有利さを過大評価しています。点差誤差のヒストグラムは同じことを点差で示しており、分布の中心がゼロにあれば、どちらかのチームへの系統的な偏りはないということです。",
          ],
        },
      ],
    },
  },

  explore: {
    en: {
      title: "About team stat trends",
      sections: [
        {
          heading: "What a rolling average shows",
          body: [
            "Season averages hide how a team is playing right now. A rolling average over the last 5 or 10 games tracks form as it changes: a shooting slump, an injury that reshapes the rotation, a defense that tightens after the trade deadline. The 5-game window reacts quickly but is noisy; the 10-game window is steadier but slower to notice a real change.",
          ],
        },
        {
          heading: "These are the model's inputs",
          body: [
            "These rolling values are built exactly the way the prediction models' inputs are: before each game, each team's recent box scores are condensed into rolling averages covering traditional stats, the four factors (shooting efficiency, turnovers, offensive rebounding and free-throw rate), hustle stats like deflections and contested shots, and player-tracking data. Comparing two teams here is a good way to see what the models were looking at when they made a pick.",
            "To see which of these stats actually move the needle on winning, see the What wins games page; to look at how two stats relate across every game, try the Stat scatter.",
          ],
        },
      ],
    },
    ja: {
      title: "チームスタッツ推移について",
      sections: [
        {
          heading: "移動平均で見えるもの",
          body: [
            "シーズン平均では、チームの「いま」の状態は分かりません。直近5試合・10試合の移動平均なら、シュートの不調、ローテーションを変えるほどのけが、トレード期限後に締まったディフェンスなど、調子の変化をそのまま追えます。5試合はすばやく反応する代わりにぶれやすく、10試合は安定している代わりに変化に気づくのが少し遅れます。",
          ],
        },
        {
          heading: "これがモデルの入力そのもの",
          body: [
            "ここに表示している移動平均は、予測モデルへの入力とまったく同じ方法で作っています。試合前に各チームの直近のボックススコアを移動平均にまとめたものです。対象は基本スタッツ、4ファクター（シュート効率・ターンオーバー・オフェンスリバウンド・フリースロー獲得率）、ディフレクションやコンテストショットなどのハッスルスタッツ、選手トラッキングのデータです。2チームを並べてみると、モデルが予測を出すときに何を見ていたのかがよく分かります。",
            "どのスタッツが勝敗に効いているかは「勝敗の分かれ目」のページで、2つのスタッツの関係を全試合で確かめたいときは「スタッツの可視化ツール」でご覧いただけます。",
          ],
        },
      ],
    },
  },

  scatter: {
    en: {
      title: "About the stat scatter",
      sections: [
        {
          heading: "One dot per team-game",
          body: [
            "Each point is one team's performance in one game, placed by the two stats you choose and colored by whether that team won. With thousands of games on one chart, patterns that are invisible in a box score become obvious: a cloud that tilts upward means the two stats rise together, and a clean split between green and red shows a stat that separates wins from losses.",
          ],
        },
        {
          heading: "The trendline and the box plots",
          body: [
            "The trendline is an ordinary least-squares fit: the straight line that best summarizes how the vertical stat changes as the horizontal one grows. A steep line with points packed tightly around it is a strong relationship; a flat line, or a wide cloud, is a weak one.",
            "When you pick specific teams, box plots along each axis show the spread of that stat in the team's wins and losses separately. If a team's winning box sits well clear of its losing box, that stat is a reliable tell for that team in particular, which is often different from the league-wide picture.",
          ],
        },
      ],
    },
    ja: {
      title: "スタッツの可視化ツールについて",
      sections: [
        {
          heading: "1点が1チームの1試合",
          body: [
            "各点は、あるチームのある1試合の成績です。選んだ2つのスタッツで位置が決まり、その試合に勝ったかどうかで色分けされます。数千試合を1枚に並べると、ボックススコアだけでは見えない傾向がはっきりします。点の集まりが右上がりなら2つのスタッツは連動しており、緑と赤がきれいに分かれていれば、そのスタッツは勝ちと負けを見分ける手がかりになります。",
          ],
        },
        {
          heading: "回帰直線と箱ひげ図",
          body: [
            "回帰直線は最小二乗法で引いた直線で、横軸の値が増えると縦軸の値がどう変わるかを一本の線にまとめたものです。傾きが急で点が線の近くに集まっていれば関係は強く、線が平らだったり点が大きく散らばっていたりすれば関係は弱いということです。",
            "チームを指定すると、各軸に沿って箱ひげ図が表示され、そのチームの勝ち試合と負け試合でのスタッツのばらつきを別々に確認できます。勝ち試合の箱が負け試合の箱からはっきり離れていれば、そのスタッツはそのチームにとって信頼できる指標です。リーグ全体の傾向とは違う結果になることも少なくありません。",
          ],
        },
      ],
    },
  },

  players: {
    en: {
      title: "How the player projections work",
      sections: [
        {
          heading: "What's being projected",
          body: [
            "For every rotation player on the slate, a separate player model projects points, rebounds, assists, steals, blocks, turnovers, threes and free throws for that night. The projection starts from the player's recent production and minutes, then adjusts for the matchup: how fast both teams play, and how stingy the opponent's defense has been lately.",
          ],
        },
        {
          heading: "Why the context columns matter",
          body: [
            "Pace is the number of possessions a team uses per 48 minutes. A fast game means more shots for everyone, so the same player tends to put up bigger raw numbers against a fast opponent. Defensive rating is points allowed per 100 possessions, which strips pace back out to measure how hard it is to score. Opponent threes allowed shows which defenses give up volume from deep. Together they explain most of the night-to-night swing in a player's projection.",
          ],
        },
        {
          heading: "Checking the projections",
          body: [
            "Once a slate is final, the table can switch from the pregame projections to what actually happened, so you can see where the model was close and where it missed. Single-game player stats are noisy by nature; for a fuller picture of how one player's projections have held up, open the player deep-dive.",
          ],
        },
      ],
    },
    ja: {
      title: "選手の成績予測のしくみ",
      sections: [
        {
          heading: "予測している数字",
          body: [
            "その日に出場が見込まれるローテーション選手全員について、選手用の別モデルが得点・リバウンド・アシスト・スティール・ブロック・ターンオーバー・3ポイント成功数・フリースロー成功数を予測します。出発点は選手の直近の成績と出場時間で、そこに対戦相手との兼ね合い、つまり両チームの試合のテンポと、相手ディフェンスの最近の堅さを加味しています。",
          ],
        },
        {
          heading: "参考列が大切な理由",
          body: [
            "ペースは48分あたりのポゼッション数です。テンポの速い試合では全員のシュート機会が増えるため、同じ選手でも速いチームが相手だと数字が伸びやすくなります。ディフェンシブレーティングは100ポゼッションあたりの失点で、ペースの影響を取り除いて「どれだけ点を取りにくい相手か」を表します。相手の被3ポイント試投数は、外からのシュートを多く許すディフェンスかどうかを示します。予測が日によって上下する理由は、たいていこの3つで説明できます。",
          ],
        },
        {
          heading: "予測の答え合わせ",
          body: [
            "試合が終わった日は、表を試合前の予測から実際の成績に切り替えられるので、どこが近くどこで外れたかを確認できます。選手の1試合の成績はもともとぶれが大きいものです。ある選手の予測がどれくらい当たってきたかをじっくり見たいときは、「選手の詳細分析」のページをご覧ください。",
          ],
        },
      ],
    },
  },

  playerExplore: {
    en: {
      title: "How to use the player deep-dive",
      sections: [
        {
          heading: "Projections next to reality",
          body: [
            "The main chart puts a player's actual production in every game next to what the projection model expected for that game. The predictions shown for past seasons are an out-of-sample backtest: each one was produced by a model trained only on earlier seasons, so it never saw the game it was predicting. That makes the comparison a fair test rather than a curve fitted to the answers.",
          ],
        },
        {
          heading: "Clearing a line",
          body: [
            "The line tool answers a common fantasy question: how often does this player get to a given number? The curve shows, for every possible line, the share of games in your chosen window that beat it. With only five or ten games the confidence interval is wide by design. Small samples really are that uncertain, and the tile says so rather than hiding it.",
            "For low-count stats like assists, steals, blocks, turnovers and threes, the model treats each game as a Poisson count around the player's projected rate. Comparing that model-implied rate with the actual hit rate shows whether a player is streakier, or steadier, than the model assumes.",
          ],
        },
        {
          heading: "Prediction error and the next matchup",
          body: [
            "The error chart shows each miss as predicted minus actual, so a consistent positive bias means the model has been too optimistic about this player. The team comparison at the bottom lines up the player's team against its next opponent on pace, efficiency and rebounding: the context the next projection will lean on most.",
          ],
        },
      ],
    },
    ja: {
      title: "選手詳細ページの使い方",
      sections: [
        {
          heading: "予測と実際を並べて見る",
          body: [
            "メインのグラフでは、選手の毎試合の実際の成績と、その試合に対するモデルの予測を並べています。過去シーズン分の予測は、それより前のシーズンだけで学習したモデルが出した事後検証（バックテスト）の値です。予測対象の試合を一度も見ていないモデルの数字なので、答えに合わせて引いた線ではなく公平な比較になっています。",
          ],
        },
        {
          heading: "基準ラインを超える確率",
          body: [
            "ラインのツールは、ファンタジーでよくある「この選手はどれくらいの頻度でこの数字に届くのか」という疑問に答えます。曲線は、考えられるすべてのラインについて、選んだ期間の試合のうち何割がそれを上回ったかを表しています。5試合や10試合では信頼区間がどうしても広くなりますが、少ない試合数ではそれだけ不確かだということで、表示でもそれを隠さずにお見せしています。",
            "アシスト・スティール・ブロック・ターンオーバー・3ポイント成功数のように数の少ないスタッツは、選手ごとの予測値を平均とするポアソン分布として扱っています。このモデル上の確率と実際に超えた割合を比べると、その選手がモデルの想定より波のあるタイプか、安定したタイプかが分かります。",
          ],
        },
        {
          heading: "予測誤差と次の対戦",
          body: [
            "誤差のグラフは「予測 − 実際」で外れ方を示します。プラス側に偏り続けているなら、モデルがその選手を高く見積もりすぎているということです。いちばん下のチーム比較では、選手のチームと次の対戦相手をペース・効率・リバウンドで並べています。次の予測が最も大きく頼りにする情報です。",
          ],
        },
      ],
    },
  },

  advisor: {
    en: {
      title: "About the fantasy advisor",
      sections: [
        {
          heading: "Grounded in the numbers on this site",
          body: [
            "The advisor is a large language model that answers fantasy basketball questions using HoopModel's own data: the nightly player projections, each player's season averages, and the pace and defensive context shown on the projections table. It is instructed to base every recommendation on those numbers and to say which ones drove the call, so its answers reflect who is actually producing right now rather than name recognition.",
          ],
        },
        {
          heading: "Getting a useful answer",
          body: [
            "Specific questions get specific answers. Paste your roster, say whether your league is points or category scoring, and include the matchup score if you're chasing a particular category. 'Who should I start at guard tonight between these three?' will get a sharper answer than 'Who is good?'.",
            "The advisor can be wrong, especially about late injury news that arrives after the nightly projections run. Treat it as a well-informed second opinion, not a final word, and it is never betting advice.",
          ],
        },
      ],
    },
    ja: {
      title: "ファンタジー・バスケ相談所について",
      sections: [
        {
          heading: "このサイトの数字にもとづく回答",
          body: [
            "この相談所の回答は、HoopModel 自身のデータを使ってファンタジーバスケットボールの質問に答える大規模言語モデルによるものです。参照するのは、毎晩更新される選手の成績予測、各選手のシーズン平均、そして成績予測の表に載っているペースや相手ディフェンスの情報です。すべての提案をこれらの数字にもとづいて行い、判断の決め手になった数字を示すよう指示しているので、知名度ではなく「いま実際に数字を残している選手」が回答に反映されます。",
          ],
        },
        {
          heading: "役に立つ回答を得るコツ",
          body: [
            "質問が具体的なほど、回答も具体的になります。ロスターを貼り付け、ポイント制かカテゴリー制かを選び、特定のカテゴリーを追いかけているなら対戦中のスコアも入力してください。「誰がいい？」よりも「今夜のガード枠、この3人のうち誰を起用すべき？」のほうが、ずっと的確な答えが返ってきます。",
            "毎晩の予測を出したあとに入ったけが情報などは反映されず、回答が外れることもあります。最終判断ではなく、データに詳しい相談相手のセカンドオピニオンとしてお使いください。賭けの助言ではありません。",
          ],
        },
      ],
    },
  },

  drivers: {
    en: {
      title: "How to read what wins games",
      sections: [
        {
          heading: "Correlation with the final margin",
          body: [
            "Each bar is the correlation between one rolling team stat, measured before the game, and that game's final point margin. A value near +1 would mean more of that stat almost always goes with a bigger win; near 0 means it tells you little on its own. In basketball, even the strongest single stats land well short of 1, because games are decided by many things at once, which is exactly why the models combine dozens of features instead of leaning on one.",
          ],
        },
        {
          heading: "Home, away and the differential",
          body: [
            "The differential view, home team's value minus away team's value, is usually the most telling, because winning is relative: a great offense matters less against an equally great one. The home-only and away-only views show whether a stat matters more for one side, and switching between the 5- and 10-game windows shows whether a signal holds up as form is measured over a longer stretch.",
          ],
        },
        {
          heading: "Correlation is not causation",
          body: [
            "A stat can correlate with winning because it reflects team quality rather than causing wins: good teams post high plus-minus because they win, not the other way round. Treat this page as a map of which signals carry information, not a recipe for winning basketball.",
          ],
        },
      ],
    },
    ja: {
      title: "「勝敗の分かれ目」の見方",
      sections: [
        {
          heading: "最終点差との相関",
          body: [
            "各棒は、試合前の時点で測ったチームスタッツの移動平均と、その試合の最終点差との相関係数です。+1 に近ければ、そのスタッツが多いほどほぼ確実に大差で勝つことを意味し、0 に近ければ単独ではほとんど何も分からないということです。バスケットボールの勝敗は多くの要素が絡み合って決まるため、最も強いスタッツでも 1 にはほど遠く、だからこそモデルは1つの指標に頼らず数十の特徴量を組み合わせています。",
          ],
        },
        {
          heading: "ホーム・アウェイ・差分",
          body: [
            "最も参考になるのは、たいてい差分（ホームの値 − アウェイの値）の表示です。勝敗は相対的なもので、どれほど強力なオフェンスも同じくらい強力な相手には効きにくいからです。ホームのみ・アウェイのみの表示では片方にとってより重要なスタッツが分かり、5試合と10試合を切り替えると、長めの期間で見ても傾向が保たれるかを確かめられます。",
          ],
        },
        {
          heading: "相関は因果ではありません",
          body: [
            "スタッツが勝敗と相関するのは、それが勝利の原因だからではなく、チームの実力を映しているからという場合もあります。強いチームの得失点差が大きいのは勝っているからで、その逆ではありません。このページは「どの指標に情報が含まれているか」の地図であって、勝つための処方箋ではないとお考えください。",
          ],
        },
      ],
    },
  },
};
