import Link from "next/link";

export default function ImpactRatings() {
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
