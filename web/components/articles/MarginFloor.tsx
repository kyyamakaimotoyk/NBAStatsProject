import Link from "next/link";
import {
  MarginHistogramFigure,
  MissByPredictorFigure,
  WithinCurveFigure,
} from "./figures/MarginFloorFigures";

export function MarginFloorEn() {
  return (
    <>
      <p>
        Every night, each of our three models predicts not just a winner but a final
        margin, like &quot;BOS by 6.&quot; Across the games on our{" "}
        <Link href="/accuracy">track record</Link>, those margins miss the real result by
        about <strong>11.7 points</strong>{" "}on average. That can look embarrassing next to
        a confident-sounding &quot;by 6.&quot;
      </p>
      <p>
        It looks less embarrassing next to the best predictor there is. The betting
        market&apos;s closing line, the final consensus of a very large and very motivated
        crowd with access to late injury news, misses the same games by about{" "}
        <strong>10.8 points</strong>. Only about 31% of games finish within five points of
        the closing line. Nobody predicts NBA margins within five points, because most of
        a margin isn&apos;t predictable before tip-off.
      </p>

      <h2>How spread out NBA margins really are</h2>
      <p>
        Across roughly 4,200 games over the last three seasons, the final margin (home
        score minus away score) has a standard deviation of about <strong>16 points</strong>.
        The typical game is decided by 10. A quarter of games are decided by five or
        fewer, and about one in five ends in a 20-point blowout.
      </p>
      <MarginHistogramFigure n={1} lang="en" />
      <p>
        That spread is the starting point. A predictor that knew nothing at all and
        guessed &quot;home by 2&quot; every night would miss by about 12.8 points.
        Everything a model learns about the two teams only chips away at that number.
        The market, with every piece of information money can buy, gets it down to just
        under 11.
      </p>
      <MissByPredictorFigure n={2} lang="en" />

      <h2>Where the unpredictable part comes from</h2>
      <p>
        An NBA game is about 100 possessions per team, and each one is a small gamble. A
        few things turn that into double-digit uncertainty:
      </p>
      <ul>
        <li>
          <strong>Shooting luck.</strong> A team that normally hits 36% from three can go
          8-for-35 or 18-for-35 on any given night without anything changing about the
          team. That one swing is worth 30 points.
        </li>
        <li>
          <strong>Game state.</strong> Once a game gets out of hand, coaches pull starters
          and the margin drifts wherever the bench units take it. Close games end with
          intentional fouls that add free throws at the end.
        </li>
        <li>
          <strong>Late information.</strong>{" "}A star ruled out an hour before tip-off
          changes the game, and the market reacts within minutes. That&apos;s a large
          part of the gap between our models and the closing line.
        </li>
      </ul>
      <p>
        None of these show up in the box scores that come before the game, and that&apos;s
        what a pre-game model learns from. The remaining error isn&apos;t a model failing
        to spot something. It&apos;s the part of basketball that hasn&apos;t happened yet.
      </p>

      <h2>So how should you read &quot;BOS by 6&quot;?</h2>
      <p>
        As the middle of a wide range, not a forecast of the final score. For our models,
        half of all predictions land within about 9.5 points of the real margin, and about
        80% land within 19. So &quot;BOS by 6&quot; really means &quot;BOS most likely wins,
        probably by somewhere between a few points and the high teens, and a loss
        wouldn&apos;t be shocking.&quot;
      </p>
      <WithinCurveFigure n={3} lang="en" />
      <p>
        That&apos;s also why we grade the models two ways. Picking the winner is a
        yes-or-no call, and that&apos;s where models genuinely differ. Margin error is
        dominated by the noise every predictor shares. That&apos;s why the{" "}
        <Link href="/performance">model comparison</Link> page shows our three models
        within a few tenths of a point of each other on margin error, while their records
        on picking winners differ more.
      </p>

      <h2>Could anyone do much better?</h2>
      <p>
        Not with information available before the game. Confirmed starting lineups,
        late scratches and player-matchup data might be worth a few tenths of a point
        each. Pile up every realistic improvement and a box-score model might reach the
        market&apos;s level, around 10.5. Getting to 8 would take information nobody has
        before tip-off. Five is a different problem altogether: that kind of precision
        only comes once part of the game has actually been played.
      </p>
      <p>
        Our goal is to get as close to the market as box scores allow, and to be upfront
        about how close we are. The track record page shows the market line on the
        same chart as our models for exactly that reason.
      </p>
    </>
  );
}

export function MarginFloorJa() {
  return (
    <>
      <p>
        3つのモデルは毎晩、勝者だけでなく「BOSが6点差で勝つ」といった最終点差も予測しています。
        <Link href="/accuracy">予測モデルの実績</Link>に載っている試合で見ると、この予測は実際の点差から
        平均で<strong>約11.7点</strong>ずれています。自信ありげな「6点差」と並べると、
        ずいぶん外れているように見えるかもしれません。
      </p>
      <p>
        ところが、世界で最も優れた予想と比べると話が変わります。賭け市場の最終予想点差は、
        直前のけが情報まで手に入れた、非常に大勢の本気の参加者による最終的な合意です。
        その市場でさえ、同じ試合で平均<strong>約10.8点</strong>外れています。
        最終予想点差から5点以内で決着する試合は、全体の約31%しかありません。
        NBAの点差を5点以内で当てられる人がいないのは、点差の大部分が試合開始前には予測しようがないからです。
      </p>

      <h2>NBAの点差は、どれくらいばらつくのか</h2>
      <p>
        直近3シーズンのおよそ4,200試合を見ると、最終点差（ホームの得点 − アウェイの得点）の
        標準偏差は<strong>約16点</strong>です。典型的な試合は10点差で決着し、4試合に1試合は5点差以内、
        5試合に1試合ほどは20点差以上の大差になります。
      </p>
      <MarginHistogramFigure n={1} lang="ja" />
      <p>
        このばらつきが出発点です。両チームについて何も知らないまま、毎晩「ホームが2点差で勝つ」と
        予想し続けた場合、平均の外れ幅は約12.8点になります。モデルが2チームについて学んだことは、
        すべてこの数字を少しずつ削るためのものです。お金で買えるあらゆる情報を持つ市場でも、
        11点をわずかに切るところまでしか下げられていません。
      </p>
      <MissByPredictorFigure n={2} lang="ja" />

      <h2>予測できない部分は、どこから来るのか</h2>
      <p>
        NBAの試合では各チームがおよそ100回ずつ攻撃し、その1回1回が小さな賭けのようなものです。
        それが積み重なって、2桁の不確かさになります。主な要因は次のとおりです。
      </p>
      <ul>
        <li>
          <strong>シュートの当たり外れ。</strong>
          普段3ポイントを36%決めるチームでも、チームとしては何も変わっていないのに、
          35本中8本の夜もあれば18本の夜もあります。この振れ幅だけで30点分です。
        </li>
        <li>
          <strong>試合展開。</strong>
          大差がつくとコーチは主力を下げ、その後の点差はベンチメンバー次第で広がりも縮まりもします。
          逆に接戦では、終盤に意図的なファウルでフリースローが増えます。
        </li>
        <li>
          <strong>直前の情報。</strong>
          試合開始1時間前にエースの欠場が決まれば試合の性格は変わり、市場は数分のうちに反応します。
          モデルと最終予想点差の差の大きな部分は、ここから生まれています。
        </li>
      </ul>
      <p>
        どれも、試合前のボックススコアには表れません。そして試合前に予測するモデルが学べるのは、
        そのボックススコアだけです。残る誤差は、モデルが何かを見落としているせいではありません。
        バスケットボールのうち、まだ起きていない部分なのです。
      </p>

      <h2>「BOSが6点差」は、どう読めばいいのか</h2>
      <p>
        最終スコアの予言ではなく、幅広い可能性の真ん中だと受け取ってください。
        当サイトのモデルでは、予測の半分が実際の点差から約9.5点以内に、約80%が19点以内に収まります。
        つまり「BOSが6点差」の本当の意味は、「BOSが勝つ可能性が最も高く、点差はおそらく数点から
        10点台後半のどこか。負けてもそれほど驚くことではない」ということです。
      </p>
      <WithinCurveFigure n={3} lang="ja" />
      <p>
        モデルを2通りの方法で採点しているのも、そのためです。勝者を当てるのは「当たりか外れか」の判定で、
        モデルごとの差がはっきり出ます。一方、点差の誤差は、どの予測にも共通するノイズが大半を占めます。
        <Link href="/performance">予測モデルの比較</Link>のページで、3つのモデルの点差誤差は
        0.数点しか違わないのに、勝敗的中率の差はそれより大きく開いているのはそのためです。
      </p>

      <h2>もっと良くすることはできるのか</h2>
      <p>
        試合前に手に入る情報だけでは、大きくは無理です。先発メンバーの確定情報、直前の欠場、
        選手同士のマッチアップのデータは、それぞれ0.数点分の改善にはなるかもしれません。
        現実的な改善をすべて積み上げれば、ボックススコアにもとづくモデルでも、市場と同じ10.5点前後に
        届く可能性はあります。しかし8点となると、試合開始前には誰も持っていない情報が必要です。
        5点はもはや別の問題で、そこまでの精度は、試合が実際にある程度進んでからでないと出せません。
      </p>
      <p>
        私たちの目標は、ボックススコアで届く範囲で市場にできるだけ近づくこと、そして今どれだけ近いのかを
        正直に示すことです。予測モデルの実績のページで、市場の予想点差をモデルと同じグラフに載せているのは、
        まさにそのためです。
      </p>
    </>
  );
}
