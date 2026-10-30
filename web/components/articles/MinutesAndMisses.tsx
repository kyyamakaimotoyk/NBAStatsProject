import Link from "next/link";
import data from "@/data/articles/minutes-and-misses.json";
import { MinutesShareFigure, PointsDecileFigure, RangeCoverageFigure } from "./figures/MinutesFigures";

const pts = data.decomp.find((d) => d.stat === "PTS")!;
const ptsRange = data.ranges.find((r) => r.stat === "PTS")!;
const reb = data.ranges.find((r) => r.stat === "REB")!;
const ast = data.ranges.find((r) => r.stat === "AST")!;
const lo = Math.round(20 - ptsRange.half90);
const hi = Math.round(20 + ptsRange.half90);

export function MinutesAndMissesEn() {
  return (
    <>
      <p>
        When a <Link href="/players">player projection</Link> misses, the first suspect is usually
        playing time. He got into foul trouble, the game was a blowout and the starters sat, the
        coach shortened the rotation. Points are minutes times scoring per minute, so if we had known
        the minutes, surely most of the miss would go away?
      </p>
      <p>
        We tested that directly, and the answer is no. Knowing the exact minutes fixes only about a
        sixth of a points projection&apos;s miss.
      </p>

      <h2>The test: hand the model the real minutes</h2>
      <p>
        For three seasons of projections, {data.n_rows.toLocaleString("en")}{" "}player-games, we
        re-scored every prediction after replacing the projected minutes with the minutes the player
        actually played, keeping everything else the same. Whatever error is left can&apos;t be blamed on
        playing time.
      </p>
      <MinutesShareFigure n={1} lang="en" />
      <p>
        For points, the average miss fell from {pts.mae} to {pts.mae_actual_min}, a{" "}
        <strong>{Math.round(pts.share)}%</strong> improvement, and points is the stat where minutes
        matter most. For steals, blocks and turnovers, knowing the minutes removes only about 2–3% of the miss.
      </p>
      <p>
        So roughly five-sixths of a points miss happens <em>per minute</em>: shots falling or not, how
        many shots a player gets, trips to the free-throw line. That remainder isn&apos;t all luck. It
        also includes our model&apos;s own error in estimating how well a player scores, and this test
        can&apos;t separate the two. What it does show is that fixing minutes wouldn&apos;t fix the
        projections.
      </p>

      <h2>The average is right at every level</h2>
      <p>
        A big single-game miss would be a problem if it were systematic: stars always shaved, role
        players always inflated. It isn&apos;t. Sorting every projection from lowest to highest and
        comparing averages, the model is on target from the deep bench to the stars.
      </p>
      <PointsDecileFigure n={2} lang="en" />
      <p>
        That&apos;s the useful way to think about a projection: an honest center for a wide spread of
        outcomes, not a prediction of the box score.
      </p>

      <h2>How wide the spread really is</h2>
      <p>
        We measure that spread with ranges built to contain the real result 9 times out of 10. For
        points the range is about <strong>±{ptsRange.half90}</strong>; for rebounds ±{reb.half90}; for
        assists ±{ast.half90}. Checked against three seasons of results, the ranges held close to the
        promised 90% for every stat.
      </p>
      <RangeCoverageFigure n={3} lang="en" />
      <p>
        In practice: a projection of 20 points means roughly {lo} to {hi}, nine nights in ten. Starters
        miss by more than bench players in raw points ({data.pts_mae_starter} vs{" "}
        {data.pts_mae_bench} on average), simply because they score more.
      </p>

      <h2>What this means for fantasy</h2>
      <ul>
        <li>
          Treat a projection as the middle of a range. Two players projected for the same 20 points
          can have very different floors and ceilings.
        </li>
        <li>
          For a specific line (&quot;will he score 25?&quot;), the{" "}
          <Link href="/players/explore">player deep-dive</Link> shows how often he has cleared it in
          recent games, which says more than the single projected number.
        </li>
        <li>
          Don&apos;t overreact to minutes news alone. It matters, but most of what decides a night
          happens once he&apos;s on the floor.
        </li>
      </ul>
    </>
  );
}

export function MinutesAndMissesJa() {
  return (
    <>
      <p>
        <Link href="/players">選手の成績予測</Link>が外れたとき、まず疑われるのは出場時間です。
        ファウルトラブルになった、大差がついて主力がベンチに下がった、コーチがローテーションを絞った。
        得点は「出場時間×1分あたりの得点」なのだから、出場時間さえわかっていれば、外れの大部分は消えるのではないか。
      </p>
      <p>
        これを実際に検証したところ、答えは「いいえ」でした。正確な出場時間がわかっても、得点予測の誤差のうち消えるのは約6分の1だけです。
      </p>

      <h2>検証：モデルに本当の出場時間を渡す</h2>
      <p>
        3シーズン分の予測（{data.n_rows.toLocaleString("ja")}試合分）について、予想出場時間を選手が実際にプレーした時間に差し替え、
        それ以外はそのままにして採点し直しました。それでも残る誤差は、出場時間のせいにはできません。
      </p>
      <MinutesShareFigure n={1} lang="ja" />
      <p>
        得点の平均誤差は{pts.mae}から{pts.mae_actual_min}に下がり、改善は<strong>{Math.round(pts.share)}%</strong>でした。
        しかも得点は、出場時間の影響が最も大きいスタッツです。スティール、ブロック、ターンオーバーでは、
        出場時間がわかっても消える誤差は2〜3%にすぎません。
      </p>
      <p>
        つまり、得点の外れの約6分の5は<em>1分ごと</em>に起きています。シュートが入るかどうか、何本打てるか、
        フリースローを何回もらえるか。この残りがすべて運というわけではありません。選手の得点力を見積もるモデル自身の誤差も含まれていて、
        この検証では両者を切り分けられないからです。それでもわかるのは、出場時間を当てられるようになっても、予測は良くならないということです。
      </p>

      <h2>平均は、どの水準でも合っている</h2>
      <p>
        1試合ごとの大きな外れが問題になるのは、それが一方向に偏っている場合です。スター選手はいつも低く、
        控え選手はいつも高く見積もる、といった偏りです。実際はそうなっていません。すべての予測を低い順に並べて平均を比べると、
        ベンチの奥の選手からスター選手まで、モデルは的を外していません。
      </p>
      <PointsDecileFigure n={2} lang="ja" />
      <p>
        予測は、ボックススコアの予言ではなく、幅広い結果の正直な中心として捉えるのが役に立ちます。
      </p>

      <h2>ばらつきは、実際どれくらい大きいのか</h2>
      <p>
        このばらつきは、実際の結果を10回に9回含むように作った幅で測っています。得点の幅は約<strong>±{ptsRange.half90}点</strong>、
        リバウンドは±{reb.half90}、アシストは±{ast.half90}です。3シーズン分の結果で確かめると、どのスタッツでも、
        約束どおりの90%に近い割合で実際の結果が幅に入っていました。
      </p>
      <RangeCoverageFigure n={3} lang="ja" />
      <p>
        実際の感覚で言えば、20得点という予測は、10試合に9試合でおよそ{lo}〜{hi}点という意味です。
        得点の誤差は先発選手のほうが控え選手より大きい（平均{data.pts_mae_starter}対{data.pts_mae_bench}）のですが、
        これは単に先発選手のほうが多く得点するからです。
      </p>

      <h2>ファンタジーでの活かし方</h2>
      <ul>
        <li>予測は幅の真ん中として扱う。同じ20得点の予測でも、下振れと上振れの幅は選手によって大きく違います。</li>
        <li>
          特定のライン（「25点を超えるか」）が気になるなら、<Link href="/players/explore">選手の詳細分析</Link>
          のページで、最近の試合でそのラインを何回超えているかを確認してください。1つの予測値よりも多くのことがわかります。
        </li>
        <li>出場時間のニュースだけに反応しすぎないこと。もちろん重要ですが、その夜を決める要素の大半は、コートに立ってから起きます。</li>
      </ul>
    </>
  );
}
