import Link from "next/link";
import data from "@/data/articles/early-season.json";
import {
  HistoryCurveFigure,
  MonthlyAccuracyFigure,
  SpreadByMonthFigure,
} from "./figures/EarlySeasonFigures";

const oct = data.months[0];
const dec = data.months.find((m) => m.m === "Dec")!;
const feb = data.months.find((m) => m.m === "Feb")!;
const apr = data.months[data.months.length - 1];
const cur = data.current;
// 95% half-width for the current-season sample, in points
const curHalf = Math.round(196 * Math.sqrt(((cur.models / 100) * (1 - cur.models / 100)) / cur.games));

export function EarlySeasonEn() {
  return (
    <>
      <p>
        The {cur.season} season is a little over a week old, and on the {cur.games} games so far
        that have a closing betting line, our three models have picked{" "}
        <strong>{cur.models}%</strong>{" "}of winners on average. That&apos;s well below the
        mid-60s they post over a full season. Is something broken?
      </p>
      <p>
        Probably not. Over the last three seasons, October has been the weakest month of the
        year for our models, and for the betting market too. Early-season games are genuinely
        harder to call, and the reason shows up in the market&apos;s own numbers.
      </p>

      <h2>October is the hardest month for everyone</h2>
      <p>
        We took every regular-season game on our{" "}
        <Link href="/accuracy">track record</Link> that also has a closing line, about 3,250
        games across three seasons, and split them by month. Our models picked{" "}
        <strong>{oct.models}%</strong> of October winners and <strong>{apr.models}%</strong>{" "}
        of April winners. The market&apos;s closing line, the final consensus of bettors who
        have every piece of news, made the same climb, from <strong>{oct.market}%</strong> to{" "}
        <strong>{apr.market}%</strong>.
      </p>
      <MonthlyAccuracyFigure n={1} lang="en" />
      <p>
        The models trail the market in every month, which is expected: the market reacts to
        late scratches and lineup decisions that come after our predictions are made. October&apos;s gap, about seven
        points, is among the widest, but it rests on only {oct.games}{" "}games. February&apos;s gap
        is wider still, at about {Math.round(feb.market - feb.models)}{" "}points. February is
        trade-deadline month, when rosters change and recent box scores briefly describe teams
        that no longer exist: the same problem as October, in miniature. That&apos;s our best
        explanation so far, not a tested one.
      </p>

      <h2>Games get more lopsided as the season goes on</h2>
      <p>
        Why would the market, with all its information, also be worse in October? The size of
        the closing spread tells you. In October the average spread is{" "}
        <strong>{oct.spread} points</strong>, and only about a quarter of games have a favorite
        by 8 or more. By April the average is <strong>{apr.spread}</strong>, and about half of
        games do.
      </p>
      <SpreadByMonthFigure n={2} lang="en" />
      <p>Two things push the spreads apart:</p>
      <ul>
        <li>
          <strong>Nobody knows yet how good the teams are.</strong>{" "}Rosters changed over the
          summer, players are returning from injuries, and last season&apos;s record is only a
          rough guide. Bettors price that uncertainty in with smaller spreads.
        </li>
        <li>
          <strong>Teams separate.</strong> Over the season, contenders pull away. By March and
          April, some teams are resting players or playing for draft position. More mismatches
          means more predictable games.
        </li>
      </ul>
      <p>
        So most of October&apos;s lower hit rate is about the games, not the predictor. A
        coin-flip game between two teams nobody can rank yet is hard for anyone.
      </p>

      <h2>Where our models fall short early</h2>
      <p>
        Our models learn from box scores: recent form over the last handful of games,
        season-to-date numbers, and a running team-strength rating. In the first week, recent
        form is built from two or three games and season-to-date numbers barely exist. The
        market can lean on preseason expectations, roster news and scouting instead.
      </p>
      <p>
        Would feeding the models more history help? Not more <em>old</em> history. We tested
        that directly: on a fixed test month, training on half a season versus everything since
        January 2022 (more than five times as many games) made no reliable difference.
      </p>
      <HistoryCurveFigure n={3} lang="en" />
      <p>
        Older seasons describe rosters and a style of play that have since moved on. What the
        models are missing in October is <em>this</em>{" "}season&apos;s games, and the only way to
        get those is to play them.
      </p>

      <h2>How to read early-season picks</h2>
      <ul>
        <li>
          Expect our models to hit in the high 50s to low 60s in October and early November.
          Even the betting market has historically managed only about {Math.round(oct.market)}%
          in October.
        </li>
        <li>
          Judge the models against the market line on the{" "}
          <Link href="/accuracy">track record</Link> page rather than against a fixed number.
        </li>
        <li>
          By December, our models have historically been around {Math.round(dec.models)}% for
          the month, and the gap to the market has been at its smallest.
        </li>
      </ul>
      <p>
        As for this season: on those {cur.games} games the market has picked {cur.market}%,
        while our models are at {cur.models}%. That&apos;s a wider gap than in a typical
        October, but {cur.games} games is a small sample, with a 95% range of roughly ±{curHalf}{" "}
        points around our number. We&apos;ll look again in our first monthly check-in at the end
        of November.
      </p>
    </>
  );
}

export function EarlySeasonJa() {
  return (
    <>
      <p>
        {cur.season}シーズンが始まって1週間あまり。最終予想点差の記録がある{cur.games}試合で、
        当サイトの3つのモデルの勝敗的中率は平均<strong>{cur.models}%</strong>です。
        シーズン全体で見たときの60%台半ばを大きく下回っています。モデルに何か問題が起きているのでしょうか。
      </p>
      <p>
        おそらく、そうではありません。過去3シーズン、10月は当サイトのモデルにとって1年で最も的中率の低い月でした。
        そしてそれは賭け市場も同じです。シーズン序盤の試合は本当に予測しにくく、その理由は市場自身の数字に表れています。
      </p>

      <h2>10月は、誰にとっても最も難しい月</h2>
      <p>
        <Link href="/accuracy">予測モデルの実績</Link>に載っているレギュラーシーズンの試合のうち、
        最終予想点差の記録があるもの（3シーズンで約3,250試合）を月別に分けてみました。
        当サイトのモデルが当てた勝者は、10月が<strong>{oct.models}%</strong>、4月が
        <strong>{apr.models}%</strong>です。あらゆる情報を手にした賭けの参加者による最終的な合意である
        市場の最終予想点差も、<strong>{oct.market}%</strong>から<strong>{apr.market}%</strong>へと、
        同じように上がっていきます。
      </p>
      <MonthlyAccuracyFigure n={1} lang="ja" />
      <p>
        どの月もモデルが市場を下回っていますが、これは予想どおりです。市場は、当サイトの予測が出たあとに決まる
        直前の欠場や先発メンバーまで織り込めるからです。10月の差は約7ポイントと大きいほうですが、もとになっているのは
        {oct.games}試合だけです。2月の差はさらに大きく、約{Math.round(feb.market - feb.models)}ポイントあります。
        2月はトレード期限の月で、ロスターが入れ替わり、直近のボックススコアがしばらくのあいだ
        「もう存在しないチーム」を表してしまいます。10月と同じ問題が、小さな規模で起きているわけです。
        ただし、これは今のところ最も有力な説明というだけで、検証はしていません。
      </p>

      <h2>シーズンが進むほど、実力差がはっきりする</h2>
      <p>
        あらゆる情報を持つ市場まで、なぜ10月は当たりにくいのでしょうか。答えは最終予想点差の大きさに表れています。
        10月の予想点差の平均は<strong>{oct.spread}点</strong>で、8点差以上の本命がいる試合は4試合に1試合ほどです。
        それが4月には平均<strong>{apr.spread}点</strong>になり、およそ半分の試合で8点差以上の本命がいます。
      </p>
      <SpreadByMonthFigure n={2} lang="ja" />
      <p>予想点差が開いていく理由は2つあります。</p>
      <ul>
        <li>
          <strong>各チームの本当の実力が、まだ誰にも分からない。</strong>
          オフシーズンにロスターが変わり、けがから戻る選手もいて、前シーズンの成績は大まかな目安にしかなりません。
          賭けの参加者はその不確かさを、小さめの予想点差という形で織り込みます。
        </li>
        <li>
          <strong>チーム間の差が開いていく。</strong>
          シーズンが進むにつれて優勝候補が抜け出し、3月・4月には主力を休ませるチームや、
          ドラフトを見据えて戦うチームも出てきます。実力差の大きい対戦が増えれば、試合は予測しやすくなります。
        </li>
      </ul>
      <p>
        つまり、10月に的中率が低いのは、予測する側よりも試合そのものの性質によるところが大きいのです。
        まだ誰も実力を見極められていないチーム同士の互角の試合は、誰にとっても難しいものです。
      </p>

      <h2>序盤にモデルが苦しむところ</h2>
      <p>
        当サイトのモデルはボックススコアから学びます。直近数試合の調子、シーズン通算の数字、そして試合ごとに更新される
        チームの強さの指標です。開幕1週目の「直近の調子」はわずか2〜3試合から計算され、シーズン通算の数字もほとんどありません。
        一方の市場は、開幕前の評価やロスターの情報、スカウティングに頼ることができます。
      </p>
      <p>
        では、モデルにもっと長い過去のデータを与えれば良くなるのでしょうか。<em>古い</em>データを増やしても効果はありません。
        実際に検証したところ、テスト期間を固定したうえで、半シーズン分だけで学習した場合と、2022年1月以降すべて
        （5倍以上の試合数）で学習した場合とで、はっきりした差は出ませんでした。
      </p>
      <HistoryCurveFigure n={3} lang="ja" />
      <p>
        古いシーズンのデータが表しているのは、すでに変わってしまったロスターやプレースタイルです。
        10月のモデルに足りないのは<em>今シーズン</em>の試合であり、それは実際に試合が行われるまで手に入りません。
      </p>

      <h2>シーズン序盤の予測の読み方</h2>
      <ul>
        <li>
          10月から11月初めにかけて、当サイトのモデルの的中率は50%台後半から60%台前半が普通です。
          賭け市場でさえ、過去の10月は約{Math.round(oct.market)}%にとどまっています。
        </li>
        <li>
          モデルの良し悪しは、決まった数字ではなく、<Link href="/accuracy">予測モデルの実績</Link>のページで
          市場の予想と比べて判断してください。
        </li>
        <li>
          過去のシーズンでは、12月になるとモデルの月間の的中率は{Math.round(dec.models)}%前後まで上がり、
          市場との差も最も小さくなっていました。
        </li>
      </ul>
      <p>
        今シーズンについては、同じ{cur.games}試合で市場が{cur.market}%、当サイトのモデルが{cur.models}%です。
        例年の10月より差は大きめですが、{cur.games}試合はとても少ないサンプルで、モデルの数字には
        ±{curHalf}ポイントほどの95%の幅があります。11月末に予定している最初の月次レポートで、あらためて確認します。
      </p>
    </>
  );
}
