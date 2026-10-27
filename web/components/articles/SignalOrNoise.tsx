import Link from "next/link";

export function SignalOrNoiseEn() {
  return (
    <>
      <p>
        Early in this project, a new group of features went into the team model and the
        results looked great: winner accuracy up 1.3 points for one model and 2.6 points
        for another, measured on a month of late-season games. It&apos;s the kind of number
        that ends up in a changelog with an exclamation mark.
      </p>
      <p>
        It was noise. Not &quot;mostly noise&quot;: when we re-ran the comparison properly,
        the new features failed every test we threw at them. This post is about how we
        found that out, and the routine every change to HoopModel now has to pass.
      </p>

      <h2>A month of games is a small sample</h2>
      <p>
        Our standard test month has about 230 games. That sounds like plenty until you ask
        how much the accuracy number would move if nothing about the model changed at all.
        Two things move it:
      </p>
      <ul>
        <li>
          <strong>Which games happen to be in the window.</strong> A month full of lopsided
          matchups is easy; a month of coin-flip games between playoff-bound teams is
          hard.
        </li>
        <li>
          <strong>Randomness in training.</strong> Most machine-learning models start from
          a random seed. Retrain the identical model with a different seed and it makes
          slightly different picks.
        </li>
      </ul>
      <p>
        We measured both directly, retraining each model with ten different seeds and
        resampling the test games a thousand times per seed. On 230 games, a model&apos;s
        accuracy wobbles by roughly <strong>±5 percentage points</strong> from those two
        sources alone. Against that backdrop, &quot;76.1% vs 76.5%&quot; isn&apos;t a
        result. It&apos;s two numbers whose error bars almost completely overlap.
      </p>

      <h2>Compare on the same games, not side by side</h2>
      <p>
        The fix is to stop comparing two separate accuracy numbers and compare the two
        models <em>game by game</em>. Both versions predict the same 230 games, so whatever
        makes a game easy or hard affects both equally and cancels out. What&apos;s left is
        the handful of games where they disagree:
      </p>
      <ul>
        <li>
          For <strong>winner picks</strong>, we count the disagreements. If the new version
          is right on 10 of them and the old one on 4, that&apos;s suggestive; 8 versus 9
          is nothing. (This is McNemar&apos;s test.)
        </li>
        <li>
          For <strong>margins</strong>, we take each game&apos;s error under both versions
          and test whether the difference is consistently negative (a paired t-test).
        </li>
        <li>
          For <strong>ranking quality</strong> (how well the win probabilities order the
          games), we resample the games and look at the distribution of the{" "}
          <em>difference</em> between the two versions.
        </li>
      </ul>
      <p>
        Paired tests are far more sensitive than eyeballing two percentages. They
        can confirm a small effect if it shows up on the same games run after run, and
        they&apos;re merciless with effects that only exist in one lucky draw.
      </p>

      <h2>What survived</h2>
      <p>We put three candidate feature groups through this routine:</p>
      <ul>
        <li>
          <strong>Team Elo ratings</strong> (a running strength rating that updates after
          every game) passed. The gain was modest, a small but consistent improvement in
          how well the probabilities ranked games, and it replicated on two different
          versions of the dataset. We kept it.
        </li>
        <li>
          <strong>Five-man lineup statistics</strong> were the source of that exciting
          &quot;+2.6 points.&quot; They failed every paired test, on every model and every
          metric. We dropped them.
        </li>
        <li>
          <strong>Opponent-adjusted rolling stats</strong> were worse than useless: they
          made margin predictions measurably <em>less</em> accurate, because they mostly
          repeated information the model already had in a noisier form. Dropped.
        </li>
      </ul>
      <p>
        One keeper out of three is a fairly typical hit rate. Most plausible-sounding
        basketball features are already captured, in some form, by the ones a model has.
      </p>

      <h2>The same trap, in tuning</h2>
      <p>
        Months later we ran our first systematic search over the team model&apos;s
        settings: how deep its trees go, how fast it learns, how hard it&apos;s
        regularized. The search scored each candidate on four earlier test months and
        found a configuration that clearly beat the original on those months.
      </p>
      <p>
        Then we tested it on a fifth month the search had never seen. Scored one seed at a
        time, it looked better there too: 79.9% against 78.2%. But once we averaged across
        seeds and compared game by game, the two configurations disagreed on 14 games and
        split them exactly <strong>7–7</strong>. The margin errors were indistinguishable.
        The search had found settings that fit those four months, not settings that
        predict basketball better. We kept the original.
      </p>
      <p>
        The interesting twist came when we ran the same procedure on the{" "}
        <Link href="/players">player projection model</Link>. There the tuned settings{" "}
        <em>did</em> hold up on held-out data: 9 of the 11 projected stats improved, with
        better fantasy-point accuracy in every test period. The one exception, blocks,
        got slightly worse, so that stat kept its original settings while the rest
        switched. Same method, opposite verdict. That&apos;s the point of having a method.
      </p>

      <h2>The rules we work by now</h2>
      <ul>
        <li>Decide the pass/fail bar <em>before</em> running the experiment, and write it down.</li>
        <li>Train with multiple seeds; never trust a single run.</li>
        <li>Compare versions with paired tests on the same games.</li>
        <li>Keep a stretch of data the selection process never touches, and let it decide.</li>
        <li>Treat a sub-one-point accuracy gain as noise until proven otherwise.</li>
      </ul>
      <p>
        None of this makes the models dramatically better on its own. What it does is
        stop them from getting quietly worse: every feature that adds noise makes the
        next real improvement harder to detect. It&apos;s also why the{" "}
        <Link href="/accuracy">track record</Link> page shows long windows by default. A
        week of results tells you very little about a model, in either direction.
      </p>
    </>
  );
}

export function SignalOrNoiseJa() {
  return (
    <>
      <p>
        このプロジェクトを始めて間もない頃、チームモデルに新しい特徴量を追加したところ、
        目を見張るような結果が出ました。レギュラーシーズン終盤の1か月分の試合で、
        勝敗的中率があるモデルでは1.3ポイント、別のモデルでは2.6ポイントも上がったのです。
        更新履歴に感嘆符付きで書きたくなるような数字でした。
      </p>
      <p>
        ところが、それはただのノイズでした。「ほとんどノイズだった」という話ではありません。
        きちんとした方法で比較し直すと、新しい特徴量はどの検定にも通らなかったのです。
        この記事では、それをどうやって見抜いたのか、そしていま HoopModel
        のあらゆる変更が通過しなければならない検証の手順を紹介します。
      </p>

      <h2>1か月分の試合は、思ったより少ない</h2>
      <p>
        普段テストに使っている1か月には、およそ230試合があります。十分な数に思えますが、
        「モデルを何ひとつ変えなかったとしたら、的中率はどれくらい動くのか」を考えると話が変わります。
        数字を動かす要因は2つあります。
      </p>
      <ul>
        <li>
          <strong>どの試合がテスト期間に入ったか。</strong>
          実力差のはっきりした対戦ばかりの月なら当てやすく、プレーオフ進出を争うチーム同士の
          五分五分の試合が続く月なら難しくなります。
        </li>
        <li>
          <strong>学習時の乱数。</strong>
          機械学習モデルの多くは、乱数のシード値を起点に学習します。まったく同じモデルでも、
          シード値を変えて学習し直すと、予測が少しずつ変わります。
        </li>
      </ul>
      <p>
        この2つの影響を実際に測ってみました。各モデルを10通りのシード値で学習し直し、
        シードごとにテスト試合を1,000回リサンプリングしたのです。すると230試合の場合、
        この2つの要因だけで的中率は<strong>±5ポイント</strong>ほど揺れることが分かりました。
        これを踏まえると、「76.1%と76.5%」の違いは結果とは呼べません。
        誤差の幅がほとんど重なっている2つの数字にすぎないのです。
      </p>

      <h2>並べて比べず、同じ試合で比べる</h2>
      <p>
        解決策は、2つの的中率を別々に見比べるのをやめて、<em>1試合ずつ</em>比べることです。
        2つのバージョンは同じ230試合を予測するので、試合ごとの当てやすさ・当てにくさは
        両者に等しく効き、比べると打ち消し合います。残るのは、両者の予測が分かれた数試合だけです。
      </p>
      <ul>
        <li>
          <strong>勝敗の予測</strong>では、予測が分かれた試合を数えます。新しいほうが10試合、
          古いほうが4試合で正解なら有望ですが、8対9なら差はないと見なします（マクネマー検定）。
        </li>
        <li>
          <strong>点差</strong>では、試合ごとに両バージョンの誤差を出し、
          その差が一貫してマイナス側に出ているかを調べます（対応のあるt検定）。
        </li>
        <li>
          <strong>勝率の並べ方の質</strong>（勝つ可能性が高い試合から低い試合へ、正しく順位付けできているか）では、
          試合をリサンプリングして、2つのバージョンの<em>差</em>がどう分布するかを見ます。
        </li>
      </ul>
      <p>
        こうした対応のある比較は、2つのパーセンテージを見比べるよりはるかに敏感です。
        同じ試合で毎回現れる効果なら、小さくても確かめられます。反対に、
        たまたま1回うまくいっただけの効果は容赦なくふるい落とされます。
      </p>

      <h2>生き残ったもの</h2>
      <p>この手順に、候補となる3つの特徴量グループをかけました。</p>
      <ul>
        <li>
          <strong>チームのイロレーティング</strong>（試合ごとに更新される通算の強さの指標）は合格しました。
          改善幅は控えめで、勝率による試合の並べ方がわずかに、しかし安定して良くなる程度でしたが、
          データセットの2つのバージョンで同じ結果が再現されたので、採用しました。
        </li>
        <li>
          <strong>5人ラインナップ単位のスタッツ</strong>は、冒頭の「+2.6ポイント」の正体です。
          どのモデル、どの指標でも、対応のある検定に1つも通らなかったため、外しました。
        </li>
        <li>
          <strong>対戦相手の強さで補正した移動平均</strong>は、役に立たないどころか逆効果でした。
          モデルがすでに持っている情報を、よりノイズの多い形で繰り返していたため、
          点差の予測がはっきりと<em>悪化</em>したのです。これも外しました。
        </li>
      </ul>
      <p>
        3つのうち1つだけ採用、というのはよくある割合です。いかにも効きそうなバスケットボールの特徴量の多くは、
        モデルがすでに持っている特徴量で、何らかの形ですでに捉えられています。
      </p>

      <h2>パラメータ調整でも、同じ落とし穴</h2>
      <p>
        何か月か後、チームモデルの設定（木をどこまで深くするか、どれだけ速く学習するか、
        どれだけ強く正則化するか）を初めて体系的に探索しました。過去4か月分のテスト期間で各候補を評価したところ、
        その4か月では元の設定をはっきり上回る組み合わせが見つかりました。
      </p>
      <p>
        そこで、探索に一度も使っていない5か月目で試しました。シード値1つずつで見ると、
        ここでも79.9%対78.2%と良く見えました。ところが、シード値をまたいで平均し、
        1試合ずつ比べると、2つの設定の予測が分かれたのは14試合で、その勝ち負けは
        きっかり<strong>7対7</strong>でした。点差の誤差も見分けがつきません。
        探索が見つけたのは、その4か月にたまたま合う設定であって、バスケットボールをより正確に予測する設定ではなかったのです。
        元の設定をそのまま使うことにしました。
      </p>
      <p>
        面白いのは、同じ手順を<Link href="/players">選手の成績予測</Link>モデルに使ったときです。
        こちらでは調整後の設定が、探索に使っていないデータでも<em>きちんと</em>通用しました。
        予測している11スタッツのうち9つが改善し、ファンタジーポイントの精度はすべてのテスト期間で向上しました。
        唯一の例外はブロックで、わずかに悪化したため、ブロックだけ元の設定を残し、ほかはすべて切り替えました。
        同じ手順で、正反対の結論。決まった手順を持つ意味はまさにそこにあります。
      </p>

      <h2>いま守っているルール</h2>
      <ul>
        <li>合格ラインは実験の<em>前</em>に決め、記録しておく。</li>
        <li>複数のシード値で学習し、1回の結果は信用しない。</li>
        <li>バージョン同士は、同じ試合を使った対応のある検定で比べる。</li>
        <li>選定に一切使わないデータを残しておき、最終判断はそのデータに委ねる。</li>
        <li>1ポイント未満の的中率の向上は、証明されるまでノイズと見なす。</li>
      </ul>
      <p>
        これだけでモデルが劇的に良くなるわけではありません。この手順の役割は、モデルが知らないうちに
        悪くなるのを防ぐことです。ノイズを持ち込む特徴量が1つ増えるたびに、次の本物の改善は見つけにくくなります。
        <Link href="/accuracy">予測モデルの実績</Link>のページが初期設定で長い期間を表示しているのも、同じ理由です。
        1週間分の結果からは、良い方向にも悪い方向にも、モデルについてほとんど何も分かりません。
      </p>
    </>
  );
}
