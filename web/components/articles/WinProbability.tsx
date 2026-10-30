import Link from "next/link";
import data from "@/data/articles/calibration.json";
import { BacktestFigure, HomePicksFigure, ReliabilityFigure } from "./figures/CalibrationFigures";

const hi = data.reliability.find((b) => b.pred > 70 && b.pred < 80)!;
const mid = data.reliability.find((b) => b.pred > 50 && b.pred < 60)!;
const feb = data.live_months.find((m) => m.m === "Feb")!;
const [rf, xgb] = data.backtest;
const cur = data.seasons[data.seasons.length - 1];
const live = data.seasons.find((s) => s.season === data.live_season)!;
const xgbWindows = data.backtest_xgb_improved;

export function WinProbabilityEn() {
  return (
    <>
      <p>
        Every prediction on <Link href="/">tonight&apos;s page</Link>{" "}comes with a win
        probability: &quot;home team 70%.&quot; What should that number mean? Not that the
        home team will win, and not that the model is &quot;70% sure&quot; in some vague sense.
        It means that across all the games where the model says 70%, the home team should win
        about 70% of them. A model whose numbers behave that way is called{" "}
        <strong>calibrated</strong>.
      </p>
      <p>
        Calibration is a separate skill from picking winners, and we learned that the hard way.
        This is the story of a fix that made our probabilities look better and our picks
        worse, and what we do now instead.
      </p>

      <h2>A random forest that seemed too timid</h2>
      <p>
        On one {data.e13.n_test}-game test month, our random forest&apos;s probabilities were off
        in a consistent direction. Games it gave about {Math.round(hi.pred)}% were won by the
        home team <strong>{Math.round(hi.obs)}%</strong> of the time. Games it gave about{" "}
        {Math.round(mid.pred)}% were won {Math.round(mid.obs)}% of the time. Its picks were
        better than its numbers admitted.
      </p>
      <ReliabilityFigure n={1} lang="en" />
      <p>
        That is a known trait of random forests: the final probability is an average over many
        trees, and averaging pulls numbers toward the middle. The standard remedy is a
        recalibration layer: fit a mapping from the model&apos;s raw probabilities to how often
        teams actually won, on games the model didn&apos;t train on, and apply it to every new
        prediction. On that test month, recalibration roughly halved the calibration error
        (from {data.e13.ece_raw} to {data.e13.ece_iso}). We added it.
      </p>

      <h2>How the fix broke the picks</h2>
      <p>
        A recalibration layer is fitted on one slice of games. If the games it later sees look
        different, the mapping can be badly wrong, and ours was. From January 2026 the forest
        picked the home team in almost every game, and in <strong>every</strong> game in
        February and March. The betting market, over the same stretch, favored the home team in
        about six games out of ten.
      </p>
      <HomePicksFigure n={2} lang="en" />
      <p>
        The forest hadn&apos;t gotten worse at telling strong teams from weak ones. The layer on
        top had pushed nearly every probability above 50%, which turned correct road-team picks
        into wrong home-team picks. In February the forest&apos;s accuracy was {feb.rf_acc}%:
        exactly the share of games the home team won. It had stopped predicting and started
        saying &quot;home&quot; every night.
      </p>
      <p>
        What made this easy to miss is that the accuracy number didn&apos;t look broken. A model
        that always picks the home team is still right whenever the home team wins, which is
        more than half the time in most months. Over the full regular season the forest picked{" "}
        {live.rf_acc}% of winners, behind XGBoost&apos;s {live.xgb_acc}%: the kind of gap that
        looks like an off year, not a broken model. The tell was in the{" "}
        <em>distribution</em> of picks, not in the hit rate.
      </p>

      <h2>What a longer test showed</h2>
      <p>
        One test month started all this, so we tested calibration properly: {rf.windows}{" "}
        monthly windows from {data.backtest_from} to {data.backtest_to}, comparing raw and
        recalibrated probabilities on the same games.
      </p>
      <BacktestFigure n={3} lang="en" />
      <ul>
        <li>
          <strong>Accuracy didn&apos;t improve</strong> for either model: about half a point
          lower on average, and anywhere from {Math.round(Math.abs(rf.acc_lo))} points worse to{" "}
          {Math.round(rf.acc_hi)} points better in a single window.
        </li>
        <li>
          <strong>The random forest didn&apos;t need it.</strong> Averaged over all the windows,
          its raw probabilities were about as well calibrated as the recalibrated ones. The
          timid month in Figure 1 was the exception, not the rule.
        </li>
        <li>
          <strong>XGBoost did need it.</strong>{" "}Recalibration lowered XGBoost&apos;s calibration
          error in {xgbWindows} of the {xgb.windows} windows and never made it worse.
        </li>
      </ul>

      <h2>What we do now</h2>
      <ul>
        <li>
          <strong>Picks always come from the raw probabilities.</strong> Recalibration can only
          change the number we display, never which team we pick.
        </li>
        <li>
          The random forest shows its raw probabilities; XGBoost shows recalibrated ones.
        </li>
        <li>
          Every retrain still measures how far a newly fitted calibration layer would move the
          share of home picks, and an extreme shift triggers an alert so someone looks at it.
        </li>
      </ul>
      <p>
        The broader lesson is to watch what a model <em>does</em>, not just how often it&apos;s
        right. The share of home picks is now one of the first things we check after a
        retrain. This season it&apos;s worth watching: over the first {cur.games} games, the
        forest has picked the home team in {cur.rf}% of them, against {cur.market_home}% for the
        market. That leans home more than the market does, but it&apos;s nothing like last
        February, and it comes from the raw model.
      </p>

      <h2>How to read the win probability on our site</h2>
      <p>
        Treat it as a frequency, not a promise. A 70% pick should lose about three times in ten,
        and when it does, that&apos;s the number working as intended. If you want to know whether
        the numbers are honest, the <Link href="/performance">model comparison</Link> page
        checks exactly this: how often the home team won at each level of predicted probability.
      </p>
    </>
  );
}

export function WinProbabilityJa() {
  return (
    <>
      <p>
        <Link href="/">本日の試合の予測</Link>には、「ホームチームの勝率70%」のように、
        すべて勝率が添えられています。この数字は何を意味するべきでしょうか。ホームチームが勝つという意味でも、
        モデルがなんとなく「7割がた自信がある」という意味でもありません。モデルが70%とした試合をすべて集めると、
        そのうち約70%でホームチームが勝つ、という意味です。数字がそのとおりに振る舞うモデルを、
        <strong>較正されている</strong>と言います。
      </p>
      <p>
        較正は、勝者を当てる力とは別の能力です。私たちはそれを痛い目にあって学びました。
        勝率の数字を良く見せるはずの修正が、かえって予測を悪くした話と、その後どうしているのかを紹介します。
      </p>

      <h2>控えめすぎるように見えたランダムフォレスト</h2>
      <p>
        {data.e13.n_test}試合のテスト期間で、ランダムフォレストの勝率には一定の方向のずれがありました。
        約{Math.round(hi.pred)}%とした試合で、ホームチームが実際に勝ったのは<strong>{Math.round(hi.obs)}%</strong>。
        約{Math.round(mid.pred)}%とした試合では{Math.round(mid.obs)}%でした。予測そのものは、
        モデル自身が示す数字よりも当たっていたのです。
      </p>
      <ReliabilityFigure n={1} lang="ja" />
      <p>
        これはランダムフォレストによくある性質です。最終的な勝率は多数の決定木の平均で、平均を取ると数字は真ん中に寄ります。
        定番の対策は再較正の層を加えることです。モデルが学習に使っていない試合で、モデルの生の勝率と実際の勝率との対応関係を求め、
        それを新しい予測すべてに当てはめます。このテスト期間では、再較正によって較正誤差がおよそ半分
        （{data.e13.ece_raw}から{data.e13.ece_iso}）になりました。そこで、この層を採用しました。
      </p>

      <h2>修正が予測を壊した経緯</h2>
      <p>
        再較正の層は、ある一部の試合をもとに作られます。その後に当てはめる試合の性質が違えば、対応関係が大きく外れることがあり、
        私たちの場合もそうなりました。2026年1月以降、ランダムフォレストはほぼすべての試合でホームチームの勝ちを予測し、
        2月と3月には<strong>すべて</strong>の試合でそうしていました。同じ時期に賭け市場がホームチームを本命としていたのは、
        10試合に6試合ほどです。
      </p>
      <HomePicksFigure n={2} lang="ja" />
      <p>
        ランダムフォレストが、強いチームと弱いチームを見分ける力を失ったわけではありません。上に重ねた層がほぼすべての勝率を
        50%より上に押し上げたため、正しかったアウェイチームの予測が、外れるホームチームの予測にひっくり返ったのです。
        2月の的中率は{feb.rf_acc}%で、その月にホームチームが勝った割合とぴったり同じでした。
        予測をやめて、毎晩「ホーム」と言っているだけになっていたわけです。
      </p>
      <p>
        見落としやすかったのは、的中率の数字が壊れているようには見えなかったからです。毎回ホームチームを選ぶモデルでも、
        ホームチームが勝てば当たるので、たいていの月は半分以上当たります。レギュラーシーズン全体でも、
        ランダムフォレストの的中率は{live.rf_acc}%で、XGBoostの{live.xgb_acc}%を下回る程度でした。
        「不調のシーズン」には見えても、「壊れたモデル」には見えない差です。異変が表れていたのは的中率ではなく、
        予測の<em>分布</em>のほうでした。
      </p>

      <h2>長い期間で検証してわかったこと</h2>
      <p>
        発端は1か月分のテストだったので、あらためて較正をきちんと検証しました。{data.backtest_from}から
        {data.backtest_to}までの{rf.windows}の月別期間で、生の勝率と再較正後の勝率を同じ試合で比べたのです。
      </p>
      <BacktestFigure n={3} lang="ja" />
      <ul>
        <li>
          <strong>的中率は、どちらのモデルでも上がりませんでした。</strong>
          平均では約0.5ポイント下がり、期間によって{Math.round(Math.abs(rf.acc_lo))}ポイント下がることも、
          {Math.round(rf.acc_hi)}ポイント上がることもありました。
        </li>
        <li>
          <strong>ランダムフォレストには、再較正は必要ありませんでした。</strong>
          全期間を平均すると、生の勝率は再較正後とほぼ同じくらい較正されていました。図1の控えめすぎた月は、例外だったのです。
        </li>
        <li>
          <strong>XGBoostには必要でした。</strong>
          XGBoostの較正誤差は、再較正によって{xgb.windows}期間中{xgbWindows}期間で小さくなり、悪化した期間は1つもありませんでした。
        </li>
      </ul>

      <h2>現在の運用</h2>
      <ul>
        <li>
          <strong>予測するチームは、常に生の勝率から決めます。</strong>
          再較正で変わるのは表示する数字だけで、どちらのチームを予測するかは変わりません。
        </li>
        <li>ランダムフォレストは生の勝率を、XGBoostは再較正後の勝率を表示します。</li>
        <li>
          再学習のたびに、新しく作った再較正の層がホームの勝ちを予測する割合をどれだけ動かすかを測っており、
          極端に動く場合は警告が出て、人が確認するようにしています。
        </li>
      </ul>
      <p>
        より大きな教訓は、モデルが何回当たったかだけでなく、モデルが<em>何をしているか</em>を見ることです。
        いまでは、再学習のたびに最初に確認する項目の1つが、ホームの勝ちを予測する割合です。今シーズンも注意して見ています。
        最初の{cur.games}試合で、ランダムフォレストがホームの勝ちを予測したのは{cur.rf}%、市場がホームを本命としたのは
        {cur.market_home}%です。市場よりホーム寄りではありますが、昨年2月とはまったく違い、しかも生のモデルによるものです。
      </p>

      <h2>当サイトの勝率の読み方</h2>
      <p>
        勝率は約束ではなく、頻度として受け取ってください。70%の予測は10回に3回ほど外れるはずで、外れたときは数字が想定どおりに働いているのです。
        数字が正直かどうかを確かめたい場合は、<Link href="/performance">予測モデルの比較</Link>のページで、
        予測した勝率の水準ごとにホームチームが実際に勝った割合を確認できます。
      </p>
    </>
  );
}
