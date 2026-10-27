import Link from "next/link";

export default function SignalOrNoise() {
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
