import Link from "next/link";
import data from "@/data/articles/count-stats.json";
import { TailFixFigure, TailGapFigure, TypicalShapeFigure } from "./figures/CountStatsFigures";

const stl = data.bins.STL.find((b) => b.bin === "0.5-1.0")!;
const topBlk = data.bins.BLK[data.bins.BLK.length - 1];
const tail = (st: string, arm: string) => data.tail.find((x) => x.stat === st && x.arm === arm)!;

export function CountStatsEn() {
  return (
    <>
      <p>
        Our <Link href="/players">player projections</Link> might say a guard will get{" "}
        <strong>0.7 steals</strong>{" "}tonight. Nobody gets 0.7 steals. He&apos;ll finish with zero,
        one, two, maybe three. For a stat like points, a single projected number is a fair summary.
        For steals and blocks, it hides the question most people actually care about: how likely is
        he to get at least one?
      </p>
      <p>
        So for these stats, we treat the projection as a <em>rate</em> and turn it into chances.
        This post shows how well that works, where it slips, and a fix we tried that made things
        worse.
      </p>

      <h2>From one number to a set of chances</h2>
      <p>
        Steals and blocks are counted events: rare, discrete, and each one more or less a separate
        piece of luck. The classic model for counts like that is the Poisson distribution. Give it an
        expected rate and it tells you how often you should see 0, 1, 2 and so on. A player expected
        for {stl.rate} steals should come away empty about <strong>{Math.round(stl.imp_p0)}%</strong>{" "}
        of the time, with exactly one about {Math.round(stl.imp_p1)}%, and with two or more about{" "}
        {Math.round(stl.imp_p2plus)}%.
      </p>
      <p>
        That&apos;s the &quot;model-implied&quot; number on the{" "}
        <Link href="/players/explore">player deep-dive</Link>. To check that it&apos;s honest, we went
        back to three seasons of predictions, {data.n_rows.toLocaleString("en")} player-games, grouped
        them by expected rate, and compared the predicted shares with what happened.
      </p>
      <TypicalShapeFigure n={1} lang="en" />
      <p>
        For typical players, it works. Within about two points, the rate gets the whole shape of
        the outcome right, not just the average.
      </p>

      <h2>Where it slips: busy defenders have more quiet nights</h2>
      <p>
        Further out, a consistent pattern appears. The higher a player&apos;s expected rate, the more
        his real games include nights with <em>none</em>, beyond what the Poisson curve predicts. For
        players expected to block two to three shots, zero-block games happened{" "}
        <strong>{topBlk.emp_p0}%</strong> of the time against {topBlk.imp_p0}% predicted, and the
        model over-forecast games with two or more ({topBlk.imp_p2plus}% predicted,{" "}
        {topBlk.emp_p2plus}% actual).
      </p>
      <TailGapFigure n={2} lang="en" />
      <p>
        The average is still right. Those players&apos; actual blocks per game match the expected rate
        closely. What&apos;s off is the spread. Poisson assumes a steady rate over the minutes played,
        and an elite shot-blocker&apos;s nights aren&apos;t steady. Our reading is that foul trouble,
        blowouts that cut minutes, and opponents who simply stop attacking the rim all produce more
        empty nights than a fixed rate would.
      </p>

      <h2>The fix that made it worse</h2>
      <p>
        We tried correcting the tails directly: a flexible mapping, learned from a held-back slice of
        each training season, from the expected rate to the real chance of a zero night or a 2+ night.
        It made things worse. For steals, the miss on the share of 2+ games roughly doubled, from{" "}
        {tail("STL", "poisson").gap.toFixed(1)} to {tail("STL", "isotonic").gap.toFixed(1)}{" "}points. For
        blocks it didn&apos;t improve on average, and swung widely from run to run.
      </p>
      <TailFixFigure n={3} lang="en" />
      <p>
        The defect is real, but the region it lives in is thin: only a few hundred player-games a
        season have an expected rate above two. A flexible correction learned from so few games
        mostly learned their noise. The better fix is probably a distribution built to allow extra
        spread, rather than a patch on top of Poisson. Until we&apos;ve tested one, the plain rate
        stays: a known, small, one-directional bias is easier to live with than a correction that
        moves unpredictably.
      </p>

      <h2>How to read steals and blocks on our site</h2>
      <ul>
        <li>
          For most players, the model-implied chances on the deep-dive can be taken at face value.
        </li>
        <li>
          For the league&apos;s busiest shot-blockers, shade the chance of a big night down a few
          points and the chance of a quiet night up.
        </li>
        <li>
          Don&apos;t read too much into a single night either way: even a perfectly calibrated 70%
          chance of a block means three games in ten without one.
        </li>
      </ul>
    </>
  );
}

export function CountStatsJa() {
  return (
    <>
      <p>
        <Link href="/players">選手の成績予測</Link>では、あるガードの今夜のスティールが
        <strong>0.7</strong>と予測されることがあります。しかし、0.7回スティールする選手はいません。
        実際には0回か1回か2回、ときには3回です。得点のようなスタッツなら1つの予測値で十分に要約できますが、
        スティールやブロックでは、多くの人が本当に知りたいこと、つまり「少なくとも1回は記録しそうか」が見えなくなってしまいます。
      </p>
      <p>
        そこでこれらのスタッツでは、予測を<em>期待値</em>として扱い、それを確率に変換しています。
        この記事では、その方法がどれくらいうまくいっているのか、どこでずれるのか、そして試してみたらかえって悪化した補正について紹介します。
      </p>

      <h2>1つの数字から、確率の組へ</h2>
      <p>
        スティールとブロックは、数えるタイプの出来事です。まれに起こり、1回ずつ区切られていて、
        それぞれがほぼ独立した運の結果です。こうした回数を表す定番のモデルがポアソン分布で、
        期待値を与えると、0回・1回・2回……がそれぞれどれくらいの頻度で起きるかを教えてくれます。
        スティールの期待値が{stl.rate}の選手なら、0回に終わるのは約<strong>{Math.round(stl.imp_p0)}%</strong>、
        ちょうど1回が約{Math.round(stl.imp_p1)}%、2回以上が約{Math.round(stl.imp_p2plus)}%になるはずです。
      </p>
      <p>
        これが<Link href="/players/explore">選手の詳細分析</Link>のページに表示している「モデル推定」です。
        この数字が正直かどうかを確かめるため、3シーズン分の予測（{data.n_rows.toLocaleString("ja")}試合分）を期待値ごとに分け、
        予測した割合と実際の割合を比べました。
      </p>
      <TypicalShapeFigure n={1} lang="ja" />
      <p>
        平均的な選手では、うまくいっています。期待値から求めた分布は、平均だけでなく結果の形全体を約2ポイント以内で捉えています。
      </p>

      <h2>ずれるところ：守備で数字を残す選手ほど、静かな夜が多い</h2>
      <p>
        分布の外側に行くと、一貫したパターンが現れます。期待値の高い選手ほど、ポアソン分布の予測を超えて
        <em>記録ゼロ</em>の夜が多くなるのです。ブロックの期待値が2〜3本の選手では、0本の試合が予測{topBlk.imp_p0}%に対して実際は
        <strong>{topBlk.emp_p0}%</strong>、2本以上の試合はモデルが多く見積もりすぎていました（予測{topBlk.imp_p2plus}%、実際{topBlk.emp_p2plus}%）。
      </p>
      <TailGapFigure n={2} lang="ja" />
      <p>
        平均はそれでも合っています。こうした選手の1試合あたりの実際のブロック数は、期待値とよく一致しています。
        ずれているのは、ばらつき方です。ポアソン分布は出場時間を通じて一定のペースを仮定していますが、
        リーグ屈指のショットブロッカーの夜は一定ではありません。私たちの解釈では、ファウルトラブル、
        大差がついて出場時間が減る試合、そしてゴール下へのアタックをやめてしまう相手チームが、
        一定のペースで考えるよりも多くの「空振りの夜」を生んでいます。
      </p>

      <h2>かえって悪化した補正</h2>
      <p>
        分布の端を直接補正することも試しました。各学習シーズンの一部を取り分け、期待値から「0回の夜」や「2回以上の夜」の
        実際の確率への柔軟な対応関係を学習させる方法です。結果は悪化でした。スティールでは、2回以上の試合の割合の誤差が
        {tail("STL", "poisson").gap.toFixed(1)}ポイントから{tail("STL", "isotonic").gap.toFixed(1)}ポイントへとほぼ倍になりました。
        ブロックでも平均では改善せず、回によって大きくぶれました。
      </p>
      <TailFixFigure n={3} lang="ja" />
      <p>
        ずれ自体は本物ですが、それが起きている領域のデータは多くありません。期待値が2を超える選手の試合は、1シーズンに数百しかないのです。
        これほど少ない試合から学習した柔軟な補正は、主にノイズを覚えてしまいました。より良い対策は、ポアソン分布に継ぎ当てをすることではなく、
        もともと余分なばらつきを表現できる分布を使うことでしょう。それを検証するまでは、期待値だけの方法を続けます。
        小さく、向きの決まったわかりやすい偏りのほうが、予測できない動き方をする補正よりも付き合いやすいからです。
      </p>

      <h2>当サイトのスティールとブロックの読み方</h2>
      <ul>
        <li>ほとんどの選手では、詳細分析のページの「モデル推定」をそのまま受け取って構いません。</li>
        <li>
          リーグ屈指のショットブロッカーについては、大量に記録する夜の確率を数ポイント低めに、
          記録ゼロの夜の確率を数ポイント高めに見積もってください。
        </li>
        <li>
          どちらの方向でも、1試合の結果を読みすぎないこと。完全に較正された「70%」でも、10試合に3試合は記録なしで終わります。
        </li>
      </ul>
    </>
  );
}
