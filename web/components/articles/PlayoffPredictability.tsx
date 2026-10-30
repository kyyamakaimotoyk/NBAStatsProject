import Link from "next/link";
import { MatchupGapFigure, PlayoffMetricsFigure } from "./figures/PlayoffFigures";

export function PlayoffPredictabilityEn() {
  return (
    <>
      <p>
        A model that picks 71% of regular-season winners sounds like it should pick
        about 71% of playoff winners too. Same teams, same sport, same model. It
        doesn&apos;t. When we tested ours, winner accuracy fell by about{" "}
        <strong>7 percentage points</strong> once the postseason started. Yet one thing
        held up almost perfectly: how honest the models were about their own uncertainty.
      </p>

      <h2>How we tested it</h2>
      <p>
        For each of five seasons, we trained the models only on regular-season games
        played before that season&apos;s playoffs. Then we scored them on three sets of
        games that all came <em>after</em>{" "}training: the last three weeks of the regular
        season (the control group), the play-in tournament, and the playoffs. Pooled
        across seasons, that&apos;s about 630 late-regular-season games and 400 playoff
        games.
      </p>

      <h2>Picking winners gets much harder</h2>
      <p>
        On the late-regular-season control games, our random forest picked{" "}
        <strong>71%</strong> of winners and our gradient-boosting model 69%. In the
        playoffs: <strong>64%</strong> and <strong>62%</strong>.
      </p>
      <p>
        A second measure fell even harder. AUC measures how well the win probabilities
        rank games, from &quot;home team almost certainly wins&quot; down to &quot;home
        team almost certainly loses.&quot; It runs from 0.5 (no better than guessing) to
        1.0 (perfect). On the control games both models scored about 0.78–0.79. In the
        playoffs they dropped to 0.60–0.64, giving up more than half their edge over
        guessing.
      </p>

      <h2>But the uncertainty stays honest</h2>
      <p>
        Alongside each margin prediction, the models produce a range meant to contain the
        real result 90% of the time. In the playoffs those ranges still contained the
        real margin <strong>88–90%</strong> of the time, right on target. The average
        margin error barely moved either, from 11.9 points to 12.1.
      </p>
      <p>
        That combination tells you something about playoff basketball. The final scores
        aren&apos;t any wilder than in the regular season; they spread out about as much
        as usual. What disappears is the ability to tell in advance <em>which side</em>{" "}
        of that spread a game will land on.
      </p>
      <PlayoffMetricsFigure n={1} lang="en" />

      <h2>What changes when the playoffs start</h2>
      <p>
        We compared the inputs the models see in late-season games against playoff games,
        and a few shifts stood out:
      </p>
      <ul>
        <li>
          <strong>The matchups are closer.</strong>{" "}Only the best teams are left, so the gap
          in team strength between the two sides is significantly smaller. Most of a
          model&apos;s accuracy comes from spotting mismatches, and the playoffs remove
          most of them.
        </li>
        <li>
          <strong>The pace slows.</strong> Playoff basketball is a half-court,
          grind-it-out game. Teams play differently from the regular-season games the
          models learned from.
        </li>
        <li>
          <strong>Series change the game.</strong>{" "}By Game 4, both coaching staffs have
          spent a week adjusting to one specific opponent. Rolling averages built over
          months of games against 29 different teams don&apos;t capture that.
        </li>
      </ul>
      <MatchupGapFigure n={2} lang="en" />
      <p>
        None of this means the model is broken. A coin flip between two evenly matched
        contenders is genuinely less predictable than a contender visiting a lottery
        team in February, and the models are correctly telling you less.
      </p>

      <h2>What about the play-in?</h2>
      <p>
        The play-in looked even less predictable, which makes sense for single-elimination
        games between middling teams. But it&apos;s only six games a year, so 30 games
        across five seasons. That&apos;s far too few to say anything with confidence, so
        we don&apos;t.
      </p>

      <h2>How to read playoff picks</h2>
      <p>
        Treat the confidence numbers with extra skepticism in the postseason. A
        &quot;65%&quot; pick in April is a weaker statement than the same number in
        January. The margin ranges, on the other hand, can be taken at face value.
        Keep it in mind when the <Link href="/accuracy">track record</Link> dips in the
        spring: a lower hit rate in the playoffs is what this study predicts, not a
        sign the model has gone wrong.
      </p>
    </>
  );
}

export function PlayoffPredictabilityJa() {
  return (
    <>
      <p>
        レギュラーシーズンで71%の勝者を当てるモデルなら、プレーオフでも71%前後は当てられそうに思えます。
        同じチーム、同じ競技、同じモデルなのですから。ところが、そうはなりません。
        当サイトのモデルで検証すると、ポストシーズンに入った途端、勝敗的中率は<strong>約7ポイント</strong>下がりました。
        それでも、ある1点だけはほぼ完璧に保たれていました。モデルが自分の予測の不確かさを正直に示せているかどうかです。
      </p>

      <h2>検証の方法</h2>
      <p>
        5シーズンそれぞれについて、そのシーズンのプレーオフより前に行われたレギュラーシーズンの試合だけで
        モデルを学習しました。そのうえで、学習<em>後</em>に行われた3種類の試合で採点しています。
        レギュラーシーズン最後の3週間（比較対照）、プレーイン・トーナメント、そしてプレーオフです。
        5シーズン合わせると、シーズン終盤の試合が約630、プレーオフの試合が約400になります。
      </p>

      <h2>勝者を当てるのは、ぐっと難しくなる</h2>
      <p>
        比較対照のシーズン終盤の試合では、ランダムフォレストが勝者の<strong>71%</strong>、
        勾配ブースティングが69%を当てました。それがプレーオフでは<strong>64%</strong>と<strong>62%</strong>に下がります。
      </p>
      <p>
        もう1つの指標は、さらに大きく落ちました。AUCは、勝率の予測で試合をどれだけ正しく順位付けできているか、
        つまり「ホームがほぼ確実に勝つ」試合から「ホームがほぼ確実に負ける」試合までを正しく並べられているかを測る指標です。
        0.5なら当てずっぽうと同じ、1.0なら完璧です。比較対照の試合では両モデルとも0.78〜0.79でしたが、
        プレーオフでは0.60〜0.64まで下がり、当てずっぽうに対する上積みの半分以上を失いました。
      </p>

      <h2>それでも、不確かさの示し方は正直なまま</h2>
      <p>
        モデルは点差の予測と一緒に、実際の結果が90%の確率で収まるはずの幅も出しています。
        プレーオフでも、この幅に実際の点差が収まった割合は<strong>88〜90%</strong>で、狙いどおりでした。
        平均点差誤差もほとんど変わらず、11.9点から12.1点になっただけです。
      </p>
      <p>
        この組み合わせから、プレーオフのバスケットボールについて分かることがあります。最終スコアの荒れ方は
        レギュラーシーズンと変わらず、ばらつきはいつもと同じくらいです。失われるのは、試合がその幅の
        <em>どちら側</em>に転ぶのかを事前に見分ける力のほうなのです。
      </p>
      <PlayoffMetricsFigure n={1} lang="ja" />

      <h2>プレーオフに入ると、何が変わるのか</h2>
      <p>
        モデルに入力されるデータを、シーズン終盤の試合とプレーオフの試合で比べてみると、
        いくつかのはっきりした違いが見つかりました。
      </p>
      <ul>
        <li>
          <strong>実力が拮抗する。</strong>
          残っているのは強いチームだけなので、両チームの実力差は明らかに小さくなります。
          モデルの的中率の大部分は実力差の大きい対戦を見抜くことから生まれますが、プレーオフにはそうした対戦がほとんど残っていません。
        </li>
        <li>
          <strong>ペースが落ちる。</strong>
          プレーオフはハーフコート中心の、我慢比べのような試合になります。モデルが学んだレギュラーシーズンの試合とは、
          戦い方そのものが違います。
        </li>
        <li>
          <strong>シリーズが試合を変える。</strong>
          第4戦にもなれば、両チームのコーチ陣は1週間かけて、たった1つの相手への対策を練り上げています。
          29の異なる相手と何か月も戦ってきた成績の平均では、それを捉えきれません。
        </li>
      </ul>
      <MatchupGapFigure n={2} lang="ja" />
      <p>
        モデルが壊れているわけではありません。実力の拮抗した優勝候補同士の五分五分の試合は、
        2月に優勝候補がドラフト上位指名権を狙う下位チームの本拠地に乗り込む試合よりも、本当に予測しにくいのです。
        モデルが示す確信が弱くなるのは、正しい反応です。
      </p>

      <h2>プレーインはどうか</h2>
      <p>
        プレーインはさらに予測しにくそうに見えました。中位のチーム同士による一発勝負なので、納得できる結果です。
        ただ、プレーインは年に6試合しかなく、5シーズン合わせても30試合です。確かなことを言うには少なすぎるので、
        ここでは結論を出しません。
      </p>

      <h2>プレーオフの予測の読み方</h2>
      <p>
        ポストシーズンでは、確信度の数字をいつもより割り引いて受け取ってください。4月の「65%」は、
        1月の同じ数字よりも弱い主張です。一方、点差の予測幅はそのまま信頼して構いません。
        春に<Link href="/accuracy">予測モデルの実績</Link>の数字が下がったときも、このことを思い出してください。
        プレーオフで的中率が下がるのは、この検証から予想されるとおりの動きであって、モデルがおかしくなったサインではありません。
      </p>
    </>
  );
}
