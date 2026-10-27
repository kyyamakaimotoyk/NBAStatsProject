import Link from "next/link";

export function ImpactRatingsEn() {
  return (
    <>
      <p>
        Public all-in-one impact metrics, the RAPTOR / EPM / DARKO family, try to boil a
        player down to one number: how much better his team does per 100 possessions
        with him on the floor, after accounting for teammates and opponents. They&apos;re
        some of the most carefully built numbers in basketball analytics, so feeding them
        into a prediction model sounds like an obvious upgrade.
      </p>
      <p>
        We tested that idea twice, once in each of our two models. Both times the answer
        was the same: no measurable improvement. Here&apos;s what we tried, and why we
        think it didn&apos;t help.
      </p>

      <h2>Test one: player projections</h2>
      <p>
        Our <Link href="/players">player projections</Link> predict counting stats
        (points, rebounds, assists and so on) for every rotation player each night. We
        added each player&apos;s <em>previous-season</em> impact rating as extra inputs.
        Using last season&apos;s numbers keeps the test honest: nothing from the future
        leaks into a prediction. About 87% of players matched to a rating each season;
        the rest were mostly rookies, who simply have no prior season.
      </p>
      <p>
        We compared the model with and without the ratings across three separate test
        periods, each retrained with three random seeds, using the paired, game-by-game
        tests described in{" "}
        <Link href="/articles/signal-or-noise/">our post on signal and noise</Link>. The
        bar for &quot;keep&quot;: a significant improvement in every test period, for at least
        two of the three seeds.
      </p>
      <p>
        Not one of the 11 stats cleared it. The biggest change anywhere was on points: an
        average error <strong>0.007 points lower</strong> per game, well inside the
        noise. The odd part is that the model clearly <em>used</em> the new inputs. They
        ranked fairly high among its inputs by importance. It just got no better at
        predicting anything with them.
      </p>

      <h2>Test two: the team model, where it should matter</h2>
      <p>
        That first null had an obvious objection. Impact metrics measure effect on the{" "}
        <em>scoreboard margin</em>, not individual box scores, so a player model is the
        wrong place for them. The team model, which predicts winners and margins, is
        their natural home.
      </p>
      <p>
        So we built a team-level version. Before each game we reconstructed each
        team&apos;s likely roster (players who&apos;d appeared recently, minus anyone
        listed out or doubtful on the official injury report) and took a
        minutes-weighted average of their prior-season ratings. On its own, the signal
        looked strong. The difference between the two teams&apos; ratings correlated with
        the final margin at <strong>0.28</strong>, and when the home team had the
        higher rating it won <strong>65%</strong> of the time.
      </p>
      <p>
        Added to the model, it did nothing. On the held-out test month: no significant
        change in accuracy, margin error or ranking quality, for any model. Pooled
        across 21 further test windows: still nothing. We also checked the case
        where we expected the most help, October through December, when this
        season&apos;s box scores are thin and last season&apos;s knowledge should be
        most valuable. There the ratings did slightly <em>worse</em>.
      </p>

      <h2>A strong signal isn&apos;t the same as new information</h2>
      <p>
        A 0.28 correlation with the margin is real. But a model doesn&apos;t need a
        feature that predicts the outcome. It needs one that predicts the part of the
        outcome its existing inputs <em>miss</em>. By the time the ratings arrived, the
        model already had:
      </p>
      <ul>
        <li>
          a running team strength rating that carries over from one season into the
          next,
        </li>
        <li>each team&apos;s recent form across dozens of box-score statistics, and</li>
        <li>information about which players are actually available tonight.</li>
      </ul>
      <p>
        Between them, those cover most of what a prior-season impact rating knows:
        which teams are good, and how much of that quality is suiting up. The ratings
        mostly told the model things it already knew, in a different unit.
      </p>
      <p>
        This is a common pattern, and worth knowing if you build models yourself. You
        can often find a feature that correlates nicely with the outcome. The test that
        matters is whether the model gets better when you add it.
      </p>

      <h2>What we haven&apos;t ruled out</h2>
      <p>
        Both tests used <em>static</em> ratings from the previous season. Some impact
        metrics update daily during the season, which could help exactly where a frozen
        number can&apos;t: a breakout player in November, or a team reshaped by a
        mid-season trade. That&apos;s still untested, and it would have to clear the same
        bar. For now, last season&apos;s ratings stay out of both models.
      </p>
    </>
  );
}

export function ImpactRatingsJa() {
  return (
    <>
      <p>
        RAPTOR、EPM、DARKOといった選手の総合インパクト指標は、1人の選手の価値を1つの数字にまとめようとするものです。
        チームメイトや対戦相手の影響を差し引いたうえで、その選手がコートにいると、100ポゼッションあたりで
        チームがどれだけ良くなるかを表します。バスケットボール分析のなかでも特に丁寧に作られた数字なので、
        予測モデルに取り入れれば精度が上がりそうに思えます。
      </p>
      <p>
        この考えを、当サイトの2つのモデルそれぞれで1回ずつ、計2回検証しました。
        結果はどちらも同じで、はっきりした改善は見られませんでした。何を試したのか、
        そしてなぜ効かなかったと考えているのかを説明します。
      </p>

      <h2>検証1: 選手の成績予測</h2>
      <p>
        <Link href="/players">選手の成績予測</Link>では、ローテーション選手全員の得点・リバウンド・
        アシストなどを毎晩予測しています。ここに、各選手の<em>前シーズンの</em>インパクト指標を入力として加えました。
        前シーズンの数字を使えば、予測に未来の情報が紛れ込むことはなく、公平な検証になります。
        指標と照合できた選手は毎シーズン約87%で、残りはほとんどが前シーズンのない新人でした。
      </p>
      <p>
        インパクト指標を入れたモデルと入れないモデルを、3つのテスト期間それぞれで、3通りのシード値で学習して比べました。
        比較には、<Link href="/articles/signal-or-noise/">シグナルとノイズについての記事</Link>で紹介した、
        試合ごとの対応のある検定を使っています。採用の条件は、3つのシード値のうち2つ以上で、
        すべてのテスト期間ではっきりした改善が出ることです。
      </p>
      <p>
        11のスタッツのうち、この条件を満たしたものは1つもありませんでした。最も大きく動いたのは得点で、
        1試合あたりの平均誤差が<strong>0.007点</strong>下がっただけ。ノイズの範囲に収まる差です。
        不思議なのは、モデルが新しい入力を明らかに<em>使っていた</em>ことです。
        重要度で見ると入力のなかでもかなり上位に入っていたのに、予測の精度は何も上がりませんでした。
      </p>

      <h2>検証2: 本来の出番であるチームモデル</h2>
      <p>
        1つ目の結果には、当然の反論があります。インパクト指標が測っているのは個人のボックススコアではなく、
        <em>スコアボード上の点差</em>への影響です。だとすれば、選手モデルに入れるのは筋違いで、
        勝者と点差を予測するチームモデルこそ、本来の出番のはずです。
      </p>
      <p>
        そこで、チーム単位の指標を作りました。各試合の前に、出場が見込まれる選手（最近出場していて、
        公式の負傷者リストで欠場・出場疑わしいとされていない選手）を割り出し、前シーズンのインパクト指標を
        出場時間で重み付けして平均したのです。単独で見ると、これは強い手がかりに見えました。
        両チームの指標の差は最終点差と<strong>0.28</strong>の相関があり、ホームチームの指標が上回っている試合では、
        ホームチームが<strong>65%</strong>勝っていたのです。
      </p>
      <p>
        ところが、モデルに加えると何も変わりませんでした。検証用の1か月では、どのモデルでも的中率・点差誤差・
        勝率の並べ方の質に、はっきりした変化はありません。さらに21のテスト期間をまとめて見ても、やはり変化なし。
        最も効果が期待できたシーズン序盤（10月から12月）、つまり今シーズンのボックススコアがまだ少なく、
        前シーズンの知識が最も役立つはずの時期も確かめましたが、そこではむしろわずかに<em>悪化</em>しました。
      </p>

      <h2>強い手がかりと、新しい情報は別物</h2>
      <p>
        点差との相関0.28は本物です。しかしモデルに必要なのは、結果を予測できる特徴量ではなく、
        既存の入力では<em>捉えきれていない</em>部分を予測できる特徴量です。
        インパクト指標を加えた時点で、モデルはすでに次のものを持っていました。
      </p>
      <ul>
        <li>シーズンをまたいで引き継がれる、チームの通算の強さの指標</li>
        <li>数十種類のボックススコアのスタッツから見た、各チームの直近の調子</li>
        <li>今夜どの選手が実際に出場できるかの情報</li>
      </ul>
      <p>
        これらを合わせると、前シーズンのインパクト指標が知っていることの大半、つまり「どのチームが強いか」と
        「その強さのうち、どれだけが今夜コートに立つか」は、すでにカバーされています。
        インパクト指標がモデルに伝えていたのは、ほとんどがすでに知っていることを別の単位で言い直したものだったのです。
      </p>
      <p>
        これはよくあるパターンなので、ご自身でモデルを作る方は覚えておいて損はありません。
        結果ときれいに相関する特徴量は、たいてい見つかります。大事なのは、それを加えたときに
        モデルが実際に良くなるかどうかです。
      </p>

      <h2>まだ否定できていないこと</h2>
      <p>
        どちらの検証も、前シーズンで<em>固定された</em>指標を使いました。インパクト指標のなかには
        シーズン中に毎日更新されるものもあり、固定された数字では対応できない場面、たとえば11月に急成長した選手や、
        シーズン途中のトレードで顔ぶれが変わったチームでは役立つかもしれません。これはまだ検証していませんし、
        検証するなら同じ基準をクリアする必要があります。それまでは、前シーズンの指標はどちらのモデルにも入れません。
      </p>
    </>
  );
}
