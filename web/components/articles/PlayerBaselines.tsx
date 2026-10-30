import Link from "next/link";
import data from "@/data/articles/player-baselines.json";
import { FantasyFigure, VsMarcelFigure, VsNaiveFigure } from "./figures/PlayerBaselinesFigures";

const s = Object.fromEntries(data.stats.map((x) => [x.stat, x]));
const marcelWins = data.stats.filter((x) => x.marcel_vs_naive < 0).length;
const modelWins = data.stats.filter((x) => x.sig_folds === data.seasons.length).length;
const sigP6 = data.p6.filter((r) => r.p < 0.05);
const p6Season = sigP6[0]?.season ?? "";
const avg = (k: "naive" | "marcel" | "xgb") => data.fantasy.reduce((a, f) => a + f[k], 0) / data.fantasy.length;

export function PlayerBaselinesEn() {
  return (
    <>
      <p>
        Before our <Link href="/players">player projections</Link>{" "}went public, the machine-learning
        model behind them had to pass one test: beat simple methods that anyone could compute in a
        spreadsheet. A complex model that can&apos;t beat a simple rule isn&apos;t earning its keep.
      </p>
      <p>
        We used two simple methods, expecting one of them to be the hard one to beat. It turned out
        to be the other way around.
      </p>

      <h2>Two simple ways to project a player</h2>
      <ul>
        <li>
          <strong>The 10-game average.</strong>{" "}Tonight&apos;s projection is the player&apos;s
          average over his last 10 games. Nothing else.
        </li>
        <li>
          <strong>Marcel.</strong>{" "}Named after &quot;Marcel the Monkey,&quot; a deliberately
          simple baseball projection system created by the analyst Tom Tango. Its idea: a player
          is what he has recently been, pulled back toward average. Our basketball version blends
          a player&apos;s per-minute production over his last 10 games, this season and last season;
          pulls that blend toward the league average, harder for players with only a few games;
          and multiplies by his projected minutes.
        </li>
      </ul>
      <p>
        Marcel has a strong reputation in baseball, where it&apos;s famously hard to beat by much.
        We expected it to be the tougher of the two. We scored all three predictors on every
        player-game in three seasons, {data.n_rows.toLocaleString("en")} in all, each season
        predicted only from the seasons before it.
      </p>

      <h2>The surprise: Marcel lost to the 10-game average</h2>
      <p>
        Marcel beat the plain 10-game average on only {marcelWins} of the 11 stats: minutes, steals
        and turnovers. On the other eight it was worse, and on 3-point attempts it was{" "}
        <strong>{s.FG3A.marcel_vs_naive.toFixed(1)}%</strong> worse.
      </p>
      <VsNaiveFigure n={1} lang="en" />
      <p>
        Our reading of the pattern: Marcel&apos;s two main ideas, leaning on past seasons and pulling
        toward the league average, help most when the last 10 games are noisy and a player&apos;s
        long-run level is the better guide. Steals and turnovers are like that. They hurt when a
        player&apos;s role changes. A guard who starts taking twice as many threes this season is
        doing something new, and a projection anchored to last season and the league average is slow
        to follow. The 10-game average follows immediately.
      </p>

      <h2>The model beat both, almost everywhere</h2>
      <p>
        Against Marcel, our model was better on {modelWins} of the 11 stats in every season, each
        confirmed with a paired test on the same player-games. The biggest gains were on 3-point
        attempts ({s.FG3A.model_vs_marcel.toFixed(1)}%) and minutes ({s.MIN.model_vs_marcel.toFixed(1)}%).
      </p>
      <VsMarcelFigure n={2} lang="en" />
      <p>
        Two exceptions are worth stating plainly:
      </p>
      <ul>
        <li>
          <strong>Steals are a tie with Marcel.</strong>{" "}We tested serving Marcel&apos;s steals number
          instead of the model&apos;s. It was significantly <em>worse</em> in {p6Season} with every
          random seed we tried, and never significantly better, so the model kept steals.
        </li>
        <li>
          <strong>Blocks are a tie with the 10-game average.</strong> On average the two are within
          a few hundredths of a percent, and the plain average was slightly ahead in{" "}
          {s.BLK.model_vs_naive_worse_folds}{" "}of the 3 seasons. For blocks, the model&apos;s extra
          machinery buys essentially nothing over the simplest possible method.
        </li>
      </ul>

      <h2>What it adds up to for fantasy</h2>
      <p>
        Fantasy scores combine all the stats, so small per-stat gains add up. Our model misses by
        about <strong>{avg("xgb").toFixed(1)}</strong> fantasy points per player-game, against{" "}
        {avg("marcel").toFixed(1)} for Marcel and {avg("naive").toFixed(1)} for the 10-game average.
      </p>
      <FantasyFigure n={3} lang="en" />
      <p>
        That&apos;s a real improvement, but notice how large all three numbers are. A single NBA game
        swings a player&apos;s line far more than any projection can anticipate, which is why the{" "}
        <Link href="/players/explore">player deep-dive</Link> shows how often a player clears a
        given line, not just a single projected number.
      </p>

      <h2>What we take from it</h2>
      <ul>
        <li>
          Test against more than one baseline. Had we used only Marcel, the model would have looked
          better than it is on blocks.
        </li>
        <li>
          A method with a strong reputation in one sport isn&apos;t automatically strong in another.
          Check it on your own data first.
        </li>
        <li>
          Say where the model doesn&apos;t win. Blocks and steals are where a simple method is as good
          as ours.
        </li>
      </ul>
      <p>
        These numbers come from the validation we ran before launch. The model has been tuned since
        (see <Link href="/articles/signal-or-noise/">our post on signal and noise</Link>), and blocks
        were the one stat where tuning didn&apos;t help either.
      </p>
    </>
  );
}

export function PlayerBaselinesJa() {
  return (
    <>
      <p>
        <Link href="/players">選手の成績予測</Link>を公開する前に、その裏にある機械学習モデルには
        1つの関門がありました。誰でも表計算ソフトで計算できるような単純な方法に勝つことです。
        単純なルールに勝てない複雑なモデルは、手間をかけるだけの価値がありません。
      </p>
      <p>
        比べる相手として2つの単純な方法を用意し、どちらか一方が手ごわい相手になると予想していました。
        ところが、結果は逆でした。
      </p>

      <h2>選手の成績を予測する、2つの単純な方法</h2>
      <ul>
        <li>
          <strong>直近10試合の平均。</strong>
          今夜の予測は、その選手の直近10試合の平均です。それ以外は何も使いません。
        </li>
        <li>
          <strong>Marcel。</strong>
          アナリストのトム・タンゴが考案した、あえて単純にした野球の成績予測方式で、「サルのマルセル」にちなんだ名前です。
          考え方は、「選手は最近の成績どおりの選手であり、ただし平均のほうへ引き戻して考える」というものです。
          当サイトのバスケットボール版では、直近10試合・今シーズン・前シーズンの出場時間あたりの成績を組み合わせ、
          それをリーグ平均のほうへ引き戻し（出場試合が少ない選手ほど強く）、予想出場時間を掛けて予測します。
        </li>
      </ul>
      <p>
        Marcelは野球の世界で評判が高く、これを大きく上回るのは難しいことで知られています。
        私たちも、2つのうち手ごわいのはMarcelのほうだと考えていました。3つの予測方法を、
        3シーズン分のすべての選手・試合（合計{data.n_rows.toLocaleString("ja")}件）で採点しました。
        各シーズンは、それより前のシーズンのデータだけを使って予測しています。
      </p>

      <h2>意外な結果：Marcelは直近10試合の平均に負けた</h2>
      <p>
        Marcelが直近10試合の平均を上回ったのは、11スタッツのうち出場時間・スティール・ターンオーバーの
        {marcelWins}つだけでした。残りの8つでは下回り、3ポイント試投数では
        <strong>{s.FG3A.marcel_vs_naive.toFixed(1)}%</strong>も悪化しました。
      </p>
      <VsNaiveFigure n={1} lang="ja" />
      <p>
        私たちはこう解釈しています。過去のシーズンに頼ること、リーグ平均へ引き戻すことというMarcelの2つの柱は、
        直近10試合がばらつきやすく、選手の長期的な水準のほうが頼りになる場合に効きます。スティールやターンオーバーがそうです。
        一方で、選手の役割が変わると裏目に出ます。今シーズンから3ポイントを倍のペースで打ち始めたガードは、
        新しいことをしているのです。前シーズンやリーグ平均を基準にした予測はその変化に追いつくのが遅く、
        直近10試合の平均はすぐに追いつきます。
      </p>

      <h2>モデルは、ほぼすべてで両方に勝った</h2>
      <p>
        当サイトのモデルは、11スタッツのうち{modelWins}つで、どのシーズンでもMarcelを上回りました。
        いずれも、同じ選手・試合を使った対応のある検定で確認しています。改善が最も大きかったのは、
        3ポイント試投数（{s.FG3A.model_vs_marcel.toFixed(1)}%）と出場時間（{s.MIN.model_vs_marcel.toFixed(1)}%）です。
      </p>
      <VsMarcelFigure n={2} lang="ja" />
      <p>はっきり書いておくべき例外が2つあります。</p>
      <ul>
        <li>
          <strong>スティールはMarcelと引き分け。</strong>
          スティールだけモデルの代わりにMarcelの数字を使う案も検証しましたが、{p6Season}シーズンでは
          試したすべてのシード値で有意に<em>悪化</em>し、有意に良くなったことは一度もなかったため、スティールもモデルのままにしました。
        </li>
        <li>
          <strong>ブロックは直近10試合の平均と引き分け。</strong>
          平均すると差は0.0数%しかなく、3シーズンのうち{s.BLK.model_vs_naive_worse_folds}シーズンでは、単純な平均のほうがわずかに上でした。
          ブロックに関しては、モデルの複雑な仕組みが、最も単純な方法に対してほとんど何も上乗せしていないのです。
        </li>
      </ul>

      <h2>ファンタジーで見るとどうなるか</h2>
      <p>
        ファンタジーのスコアはすべてのスタッツを合算するので、スタッツごとの小さな改善が積み重なります。
        当サイトのモデルの誤差は、選手1人・1試合あたり約<strong>{avg("xgb").toFixed(1)}</strong>ファンタジーポイントで、
        Marcelは{avg("marcel").toFixed(1)}、直近10試合の平均は{avg("naive").toFixed(1)}でした。
      </p>
      <FantasyFigure n={3} lang="ja" />
      <p>
        確かな改善ですが、3つの数字がどれも大きいことにも注目してください。NBAの1試合で選手の成績が振れる幅は、
        どんな予測にも見通せないほど大きいのです。<Link href="/players/explore">選手の詳細分析</Link>
        のページで、予測を1つの数字だけでなく、ある数字を超える試合がどれくらいあるかでも示しているのはそのためです。
      </p>

      <h2>この検証から学んだこと</h2>
      <ul>
        <li>基準は1つでなく、複数用意して比べる。Marcelだけを相手にしていたら、ブロックでのモデルの実力を過大評価していたはずです。</li>
        <li>ある競技で評判の高い方法が、別の競技でも強いとは限らない。まず自分のデータで確かめる。</li>
        <li>モデルが勝てないところも明示する。ブロックとスティールでは、単純な方法でも当サイトのモデルと同じくらい当たります。</li>
      </ul>
      <p>
        ここで紹介した数字は、公開前に行った検証のものです。モデルはその後パラメータを調整していますが
        （<Link href="/articles/signal-or-noise/">モデル変更の判断基準についての記事</Link>を参照）、
        調整でも改善しなかった唯一のスタッツが、やはりブロックでした。
      </p>
    </>
  );
}
