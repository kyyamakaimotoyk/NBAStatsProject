import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About — HoopModel",
  description:
    "How HoopModel works: the data, the models, the nightly cycle, and how every prediction gets graded in public.",
};

// Pure static content — no client fetch, so this stays a server component.
export default function AboutPage() {
  return (
    <section>
      <h1>About HoopModel</h1>
      <p className="subtle">
        A machine-learning side project built by Kai Yamamoto that predicts NBA game winners (and their winning margins),
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
        <Link href="/explore">Explore</Link> and <Link href="/scatter">Scatter</Link>{" "}
        pages, and see which of these signals actually track winning on{" "}
        <Link href="/drivers">What wins games</Link>.
      </p>

      <h2>The models</h2>
      <p>
        Three independent models make every pick: a random-forest ensemble, a gradient boosting model, and a neural
        network. Each predict a home-team win probability, and an expected point margin. The models don't always agree.
        Their strengths and weaknesses are compared openly on the <Link href="/performance">Model lab</Link> page.
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
        Betting advice. The predictions are models developed, and its outputs published for curiosity,
        learning, and record-keeping only. It is purely for educational purposes.
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
