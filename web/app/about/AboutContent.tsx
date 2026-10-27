"use client";

import Link from "next/link";
import { useLang } from "@/lib/i18n";

// Long-form prose with inline links reads better as two full JSX versions
// than as a dictionary shredded into sentence fragments. The Japanese is a
// transcreation, not a sentence-by-sentence translation — keep it that way.

const LINKEDIN_URL = "https://www.linkedin.com/in/kaiyamamoto1/";

function AboutEnglish() {
  return (
    <section>
      <h1>About HoopModel</h1>
      <p className="subtle">
        A side project built by Kai Y.
        that predicts NBA game winners (and their winning margins),
        and keeps score on itself, in public.
      </p>

      <h2>What this is</h2>
      <p>
        Every night with games on the schedule, three models each predict the winner and
        the point margin for every matchup. The picks are logged before tip-off, graded
        against the final score after the buzzer, and published here — hits, misses,
        and everything on the <Link href="/accuracy">track record</Link>. Nothing is
        edited after the fact.
      </p>

      <h2>The data</h2>
      <p>
        The models learn from years of NBA team box scores — traditional counting stats plus
        four-factors, hustle, player tracking, and scoring breakdowns. Before each game, every
        team&apos;s recent play is distilled into rolling features: how they&apos;ve
        shot, rebounded, defended, and won over their last 5/10 games, at home and
        on the road. You can poke at the same data on the{" "}
        <Link href="/explore">Team stats</Link> and <Link href="/scatter">Stat scatter</Link>{" "}
        pages, and see which of these signals actually track winning on{" "}
        <Link href="/drivers">What wins games</Link>.
      </p>

      <h2>The models</h2>
      <p>
        Three independent models make every pick: a random-forest ensemble, a gradient boosting model, and a neural
        network. Each predict a home-team win probability, and an expected point margin. The models don&apos;t always agree.
        Their strengths and weaknesses are compared openly on the <Link href="/performance">Compare models</Link> page.
      </p>

      <h2>The nightly cycle</h2>
      <p>
        A scheduled batch job runs every morning: it pulls the latest results, refreshes
        each team&apos;s rolling form, grades yesterday&apos;s predictions, and writes
        tonight&apos;s picks to the database. The site you&apos;re reading is a static
        page that fetches those stored predictions — no model runs when you load a page,
        which is why it&apos;s fast.
      </p>

      <h2>Keeping myself honest</h2>
      <p>
        Accuracy alone can flatter, so the track record also shows the average margin
        miss, probability calibration, and a comparison against the betting
        market&apos;s closing pre-game spread, which I believe is the strongest public benchmark for a game&apos;s
        margin. The market is very hard to beat; showing the gap either way is the
        point.
      </p>

      <h2>What this is not</h2>
      <p>
        Betting advice. The published models and their respective outputs are published for curiosity,
        learning, and record-keeping only. It is purely for an educational purpose.
      </p>

      <h2>Under the hood</h2>
      <p>
        For the technically curious: the models are Python (scikit-learn and PyTorch),
        trained on features engineered from boxscore history in MySQL. Predictions are
        batch-computed on a nightly schedule in AWS (Fargate), stored in a database, and
        served by a small read-only API. This site is a static Next.js app on S3 behind
        CloudFront, and the whole stack is defined in Terraform and deployed by CI on
        every push.
      </p>
    </section>
  );
}

function AboutJapanese() {
  return (
    <section>
      <h1>HoopModelについて</h1>
      <p className="subtle">
        HoopModelは、私が趣味で運営している機械学習プロジェクトです。NBAの試合の勝敗と点差を
        毎晩予測し、その結果をすべて公開しています。
      </p>

      <h2>サイトの概要</h2>
      <p>
        試合が予定されている日は、毎晩3つのモデルが全カードの勝者と点差を予測します。
        予測は試合開始前に記録し、試合終了後に実際のスコアと照らし合わせて採点します。
        結果は当たり外れを問わずすべて<Link href="/accuracy">予測モデルの実績</Link>のページに掲載し、
        後から修正することはありません。
      </p>

      <h2>データ</h2>
      <p>
        モデルの学習データは、過去数シーズン分のNBAチームボックススコアです。得点やリバウンドといった
        基本スタッツに加え、フォーファクター、ハッスル系、選手トラッキング、得点の内訳なども
        利用しています。試合前には、各チームの直近5試合・10試合の傾向（シュートの調子、リバウンド、
        守備、勝敗など）をホーム・アウェイ別に集計し、特徴量として整理します。これらのデータは
        <Link href="/explore">チーム成績のトレンド</Link>や<Link href="/scatter">スタッツの可視化ツール</Link>のページで
        実際に確認できます。また、どのスタッツが勝敗に結びついているかは
        <Link href="/drivers">勝敗の分かれ目</Link>のページで見ることができます。
      </p>

      <h2>モデル</h2>
      <p>
        予測には、互いに独立した3つのモデルを使っています。ランダムフォレスト、勾配ブースティング、
        ニューラルネットワークの3つです。各モデルはホームチームの勝率と予測点差を出力します。
        3つの予測は一致しないことも多く、それぞれの得意・不得意は<Link href="/performance">予測モデルの比較</Link>
        のページで確認できます。
      </p>

      <h2>毎晩の処理</h2>
      <p>
        毎朝、定時のバッチ処理が実行されます。前日の試合結果を取り込み、各チームの直近成績を更新し、
        前日の予測を採点したうえで、その夜の予測をデータベースに書き込みます。このサイト自体は
        保存された予測を表示するだけの静的なページで、閲覧時にモデルが動くことはありません。
        表示が速いのはそのためです。
      </p>

      <h2>正直な評価のために</h2>
      <p>
        的中率だけでは、モデルの実力を正しく評価できません。そこで予測モデルの実績のページでは、点差の平均誤差や
        勝率予測のキャリブレーションに加えて、賭け市場の最終予想点差との比較も
        掲載しています。市場の予想は、点差予測の基準としては最も厳しい公開ベンチマークで、
        上回れることはめったにありません。それでも、その差を隠さずに示すことがこのサイトの趣旨です。
      </p>

      <h2>免責事項</h2>
      <p>
        本サイトは賭けを推奨するものではありません。掲載しているモデルと予測は、興味と学習、
        そして記録のために公開しているものであり、あくまで教育目的のプロジェクトです。
      </p>

      <h2>技術構成</h2>
      <p>
        モデルはPython（scikit-learnおよびPyTorch）で実装し、MySQLに保存したボックススコア履歴から
        特徴量を作成して学習しています。予測はAWS（Fargate）上で毎晩バッチ計算し、データベースに
        保存したものを小規模な読み取り専用APIで配信しています。サイト本体はS3とCloudFrontで配信する
        静的なNext.jsアプリで、インフラ全体をTerraformで管理し、pushごとにCIで自動デプロイしています。
      </p>
    </section>
  );
}

export default function AboutContent() {
  const { lang } = useLang();
  return lang === "ja" ? <AboutJapanese /> : <AboutEnglish />;
}
