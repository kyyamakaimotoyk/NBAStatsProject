import Link from "next/link";

export default function MarginFloor() {
  return (
    <>
      <p>
        Every night, each of our three models predicts not just a winner but a final
        margin, like &quot;BOS by 6.&quot; Across the games on our{" "}
        <Link href="/accuracy">track record</Link>, those margins miss the real result by
        about <strong>11.5 points</strong> on average. That can look embarrassing next to
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
      <p>
        That spread is the starting point. A predictor that knew nothing at all and
        guessed &quot;home by 2&quot; every night would miss by about 12.7 points.
        Everything a model learns about the two teams only chips away at that number.
        The market, with every piece of information money can buy, gets it down to just
        under 11.
      </p>

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
          <strong>Late information.</strong> A star ruled out an hour before tip-off
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
