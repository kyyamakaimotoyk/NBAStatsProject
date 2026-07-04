"use client";

import { useEffect, useMemo, useState } from "react";
import { getFeatureTimeseries, type FeatureTimeseriesRow } from "@/lib/api";
import { FEATURE_CATALOG, allTeams, teamSeries } from "@/lib/explore";
import FeatureChart from "@/components/FeatureChart";

export default function ExplorePage() {
  const [feature, setFeature] = useState("PTS");
  const [rollWindow, setRollWindow] = useState<"L5" | "L10">("L5");
  const [rows, setRows] = useState<FeatureTimeseriesRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [teams, setTeams] = useState<string[]>([]);

  useEffect(() => {
    setRows(null);
    setError(null);
    getFeatureTimeseries(feature, rollWindow, 365)
      .then((r) => setRows(r.rows))
      .catch((e) => setError(String(e)));
  }, [feature, rollWindow]);

  const available = useMemo(() => (rows ? allTeams(rows) : []), [rows]);

  // Default-select the first two teams once data is available.
  useEffect(() => {
    if (available.length > 0 && teams.length === 0) setTeams(available.slice(0, 2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [available]);

  const series = useMemo(
    () => (rows ? teamSeries(rows, teams) : { data: [], teams: [] }),
    [rows, teams],
  );

  return (
    <section>
      <h1>Explore the data</h1>
      <p className="subtle">
        Track any team&apos;s rolling form (last 5 or 10 games) for a chosen stat across
        the season.
      </p>

      <div className="controls explore-controls">
        <label>
          Stat:{" "}
          <select value={feature} onChange={(e) => setFeature(e.target.value)}>
            {FEATURE_CATALOG.map((c) => (
              <optgroup key={c.category} label={c.category}>
                {c.features.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          Window:{" "}
          <select
            value={rollWindow}
            onChange={(e) => setRollWindow(e.target.value as "L5" | "L10")}
          >
            <option value="L5">Last 5</option>
            <option value="L10">Last 10</option>
          </select>
        </label>
        <label className="team-select">
          Teams (ctrl/cmd-click for multiple):
          <select
            multiple
            size={5}
            value={teams}
            onChange={(e) => setTeams([...e.target.selectedOptions].map((o) => o.value))}
          >
            {available.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="status error">Couldn&apos;t load: {error}</p>}
      {!error && !rows && <p className="status">Loading…</p>}
      {!error && rows && rows.length === 0 && (
        <p className="status">No data for this stat yet.</p>
      )}
      {!error && rows && rows.length > 0 && (
        <>
          <h2>
            {feature} ({rollWindow}) — rolling average
          </h2>
          <FeatureChart
            data={series.data}
            teams={teams}
            yLabel={`${feature} (${rollWindow} rolling avg)`}
          />
        </>
      )}
    </section>
  );
}
