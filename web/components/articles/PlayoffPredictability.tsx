import Link from "next/link";

export default function PlayoffPredictability() {
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
        games that all came <em>after</em> training: the last three weeks of the regular
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

      <h2>What changes when the playoffs start</h2>
      <p>
        We compared the inputs the models see in late-season games against playoff games,
        and a few shifts stood out:
      </p>
      <ul>
        <li>
          <strong>The matchups are closer.</strong> Only the best teams are left, so the gap
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
          <strong>Series change the game.</strong> By Game 4, both coaching staffs have
          spent a week adjusting to one specific opponent. Rolling averages built over
          months of games against 29 different teams don&apos;t capture that.
        </li>
      </ul>
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
