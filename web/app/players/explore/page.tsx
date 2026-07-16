"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  getPlayerDirectory,
  getPlayerGamelog,
  getTeamContext,
  type PlayerDirEntry,
  type PlayerGamelogResponse,
  type TeamContextResponse,
} from "@/lib/api";
import {
  STATS,
  windowRows,
  predKey,
  buildDistribution,
  buildErrorDistribution,
  windowStats,
  defaultLine,
  clearRate,
  poissonClearProb,
  clearCurve,
  type StatKey,
  type WindowKey,
} from "@/lib/playerExplore";
import { useLang } from "@/lib/i18n";
import PlayerStatChart, { type PlayerChartRow } from "@/components/PlayerStatChart";
import PlayerDistChart from "@/components/PlayerDistChart";
import ClearCurveChart from "@/components/ClearCurveChart";
import TeamComparePanel from "@/components/TeamComparePanel";

const WINDOWS: WindowKey[] = ["L5", "L10", "season", "three"];

export default function PlayersExplorePage() {
  const { t } = useLang();
  const [dir, setDir] = useState<PlayerDirEntry[] | null>(null);
  const [teamId, setTeamId] = useState<number | null>(null);
  const [personId, setPersonId] = useState<number | null>(null);
  const [statKey, setStatKey] = useState<StatKey>("pts");
  const [win, setWin] = useState<WindowKey>("season");
  // null = auto (window median). Kept across window switches so a fixed line
  // can be compared between windows; reset when the stat (scale) changes.
  const [line, setLine] = useState<number | null>(null);
  const [log, setLog] = useState<PlayerGamelogResponse | null>(null);
  const [ctx, setCtx] = useState<TeamContextResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Directory once; default to the first team + its first player.
  useEffect(() => {
    getPlayerDirectory()
      .then((r) => {
        setDir(r.players);
        const first = r.players.find((p) => p.team_id != null);
        if (first) {
          setTeamId(first.team_id);
          setPersonId(first.person_id);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  const teams = useMemo(() => {
    const byTeam = new Map<number, { abbrev: string; players: PlayerDirEntry[] }>();
    for (const p of dir ?? []) {
      if (p.team_id == null) continue;
      const entry = byTeam.get(p.team_id) ?? { abbrev: p.team_abbrev ?? "?", players: [] };
      entry.players.push(p);
      byTeam.set(p.team_id, entry);
    }
    return [...byTeam.entries()]
      .map(([id, v]) => ({ team_id: id, ...v }))
      .sort((a, b) => a.abbrev.localeCompare(b.abbrev));
  }, [dir]);

  const teamPlayers = useMemo(
    () => teams.find((tm) => tm.team_id === teamId)?.players ?? [],
    [teams, teamId],
  );

  useEffect(() => {
    if (personId == null) return;
    setLog(null);
    getPlayerGamelog(personId)
      .then(setLog)
      .catch((e) => setError(String(e)));
  }, [personId]);

  useEffect(() => {
    if (teamId == null) return;
    setCtx(null);
    getTeamContext(teamId)
      .then(setCtx)
      .catch(() => setCtx(null)); // context is a side panel; never block the page
  }, [teamId]);

  const stat = STATS.find((s) => s.key === statKey)!;
  const rows = useMemo(() => (log ? windowRows(log.rows, win) : []), [log, win]);

  const chartRows: PlayerChartRow[] = useMemo(
    () =>
      rows.map((r) => ({
        label: win === "three" ? r.game_date.slice(2) : r.game_date.slice(5),
        date: r.game_date,
        opp: r.opp,
        is_home: r.is_home,
        actual: r[statKey] != null ? Number(r[statKey]) : null,
        pred: r[predKey(statKey)] != null ? Number(r[predKey(statKey)]) : null,
        min: r.min != null ? Number(r.min) : null,
        predMin: r.pred_min != null ? Number(r.pred_min) : null,
        pf: r.pf != null ? Number(r.pf) : null,
      })),
    [rows, statKey, win],
  );

  const actuals = useMemo(
    () =>
      rows
        .map((r) => r[statKey])
        .filter((v): v is number => v != null)
        .map(Number),
    [rows, statKey],
  );

  // Model's Poisson rate for the window: mean prediction, falling back to the
  // actuals when too few games are covered. Shared by the distribution overlay
  // and the clearing-a-line panel.
  const lambda = useMemo(() => {
    if (!stat.poisson) return undefined;
    const preds = rows
      .map((r) => r[predKey(statKey)])
      .filter((v): v is number => v != null)
      .map(Number);
    const base = preds.length >= 3 ? preds : actuals;
    if (base.length === 0) return undefined;
    return base.reduce((a, b) => a + b, 0) / base.length;
  }, [rows, statKey, stat.poisson, actuals]);

  const dist = useMemo(
    () => buildDistribution(actuals, statKey, lambda),
    [actuals, statKey, lambda],
  );

  const stats = useMemo(() => windowStats(actuals), [actuals]);
  const effLine = line ?? (actuals.length > 0 ? defaultLine(actuals) : 0.5);
  const rate = useMemo(() => clearRate(actuals, effLine), [actuals, effLine]);
  const curve = useMemo(() => clearCurve(actuals, statKey), [actuals, statKey]);
  const modelProb =
    stat.poisson && lambda !== undefined ? poissonClearProb(lambda, effLine) : null;

  const errDist = useMemo(() => buildErrorDistribution(rows, statKey), [rows, statKey]);

  const changeTeam = (id: number) => {
    setTeamId(id);
    const first = (dir ?? []).find((p) => p.team_id === id);
    setPersonId(first ? first.person_id : null);
  };

  return (
    <section>
      <h1>{t.playersExplore.title}</h1>
      <p className="subtle">
        {t.playersExplore.subtitle}{" "}
        <Link href="/players">{t.playersExplore.dailyLink}</Link>
      </p>

      <div className="controls explore-controls">
        <label>
          {t.playersExplore.teamLabel}{" "}
          <select value={teamId ?? ""} onChange={(e) => changeTeam(Number(e.target.value))}>
            {teams.map((tm) => (
              <option key={tm.team_id} value={tm.team_id}>
                {tm.abbrev}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.playersExplore.playerLabel}{" "}
          <select value={personId ?? ""} onChange={(e) => setPersonId(Number(e.target.value))}>
            {teamPlayers.map((p) => (
              <option key={p.person_id} value={p.person_id}>
                {p.player_name ?? p.person_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.playersExplore.statLabel}{" "}
          <select
            value={statKey}
            onChange={(e) => {
              setStatKey(e.target.value as StatKey);
              setLine(null); // a line only makes sense on the stat's own scale
            }}
          >
            {STATS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t.playersExplore.windowLabel}{" "}
          <select value={win} onChange={(e) => setWin(e.target.value as WindowKey)}>
            {WINDOWS.map((w) => (
              <option key={w} value={w}>
                {t.playersExplore.windows[w]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="status error">{t.playersExplore.errLoad(error)}</p>}
      {!error && !dir && <p className="status">{t.playersExplore.loading}</p>}
      {!error && dir && dir.length === 0 && <p className="status">{t.playersExplore.noData}</p>}

      {!error && log && (
        <>
          {stats && rate && (
            <>
              <h2>{t.playersExplore.lineTitle(stat.label)}</h2>
              <div className="controls explore-controls">
                <label className="inline">
                  {t.playersExplore.lineLabel}{" "}
                  <input
                    className="line-input"
                    type="number"
                    step={0.5}
                    min={0}
                    value={effLine}
                    onChange={(e) =>
                      setLine(e.target.value === "" ? null : Number(e.target.value))
                    }
                  />
                </label>
              </div>
              <ClearCurveChart
                data={curve}
                line={effLine}
                pct={rate.pct}
                statLabel={stat.label}
                onSelect={setLine}
              />
              <div className="cards">
                <div className="card">
                  <div className="card-title">{t.playersExplore.tileGames}</div>
                  <div className="card-metric">{stats.n}</div>
                  <div className="card-sub">{t.playersExplore.windows[win]}</div>
                </div>
                <div className="card">
                  <div className="card-title">{t.playersExplore.tileAvg}</div>
                  <div className="card-metric">{stats.mean.toFixed(1)}</div>
                  <div className="card-sub">
                    {stat.label} {t.playersExplore.perGame}
                  </div>
                </div>
                <div className="card">
                  <div className="card-title">{t.playersExplore.tileSd}</div>
                  <div className="card-metric">{stats.sd != null ? stats.sd.toFixed(1) : "—"}</div>
                  <div className="card-sub">{t.playersExplore.sdSub}</div>
                </div>
                <div className="card">
                  <div className="card-title">{t.playersExplore.tileOver(String(effLine))}</div>
                  <div className="card-metric">{rate.pct.toFixed(0)}%</div>
                  <div className="card-sub">
                    {t.playersExplore.overSub(
                      rate.k,
                      rate.n,
                      rate.ciLo.toFixed(0),
                      rate.ciHi.toFixed(0),
                    )}
                  </div>
                </div>
                {modelProb != null && (
                  <div className="card">
                    <div className="card-title">{t.playersExplore.tileModel}</div>
                    <div className="card-metric">{(modelProb * 100).toFixed(0)}%</div>
                    <div className="card-sub">{t.playersExplore.modelSub}</div>
                  </div>
                )}
              </div>
              <p className="caption">{t.playersExplore.lineCaption}</p>
            </>
          )}

          <h2>
            {t.playersExplore.chartHeading(log.player_name ?? "", stat.label)}
          </h2>
          <PlayerStatChart data={chartRows} statLabel={stat.label} />
          <p className="caption">{t.playersExplore.backtestNote}</p>

          <h2>{t.playersExplore.distHeading(stat.label)}</h2>
          <PlayerDistChart
            bins={dist}
            barName={t.playersExplore.shareOfGames}
            poissonName={stat.poisson ? t.playersExplore.poissonExpected : undefined}
            yCap={stat.poisson ? 0.8 : 0.4}
          />
          {stat.poisson && <p className="caption">{t.playersExplore.distPoissonNote}</p>}

          <h2>{t.playersExplore.errHeading(stat.label)}</h2>
          {errDist.n === 0 ? (
            <p className="status">{t.playersExplore.noPreds}</p>
          ) : (
            <>
              <PlayerDistChart
                bins={errDist.bins}
                barName={t.playersExplore.shareOfGames}
                yCap={0.5}
              />
              <p className="caption">
                {t.playersExplore.errSummary(errDist.n, errDist.mae ?? 0, errDist.bias ?? 0)}
              </p>
            </>
          )}
        </>
      )}
      {!error && personId != null && !log && <p className="status">{t.playersExplore.loading}</p>}

      {ctx && (
        <>
          <h2>{t.playersExplore.teamCompareHeading}</h2>
          <TeamComparePanel ctx={ctx} />
        </>
      )}
    </section>
  );
}
