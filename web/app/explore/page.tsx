"use client";

import { useEffect, useMemo, useState } from "react";
import { getFeatureTimeseries, type FeatureTimeseriesRow } from "@/lib/api";
import { FEATURE_CATALOG, allTeams, teamSeries } from "@/lib/explore";
import { useLang } from "@/lib/i18n";
import FeatureChart from "@/components/FeatureChart";
import TeamPicker from "@/components/TeamPicker";

export default function ExplorePage() {
  const { t } = useLang();
  const [feature, setFeature] = useState("PTS");
  const [rollWindow, setRollWindow] = useState<"L5" | "L10">("L5");
  const [days, setDays] = useState(365);
  const [rows, setRows] = useState<FeatureTimeseriesRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [teams, setTeams] = useState<string[]>([]);

  useEffect(() => {
    setRows(null);
    setError(null);
    getFeatureTimeseries(feature, rollWindow, days)
      .then((r) => setRows(r.rows))
      .catch((e) => setError(String(e)));
  }, [feature, rollWindow, days]);

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

  const windowLabel = rollWindow === "L5" ? t.explore.last5 : t.explore.last10;

  return (
    <section>
      <h1>{t.explore.title}</h1>
      <p className="subtle">{t.explore.subtitle}</p>

      <div className="controls explore-controls">
        <label>
          {t.explore.statLabel}{" "}
          <select value={feature} onChange={(e) => setFeature(e.target.value)}>
            {FEATURE_CATALOG.map((c) => (
              <optgroup key={c.category} label={t.explore.categories[c.category] ?? c.category}>
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
          {t.explore.windowLabel}{" "}
          <select
            value={rollWindow}
            onChange={(e) => setRollWindow(e.target.value as "L5" | "L10")}
          >
            <option value="L5">{t.explore.last5}</option>
            <option value="L10">{t.explore.last10}</option>
          </select>
        </label>
        <label>
          {t.explore.horizonLabel}{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {t.explore.horizons.map((h) => (
              <option key={h.days} value={h.days}>
                {h.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <TeamPicker
        options={available}
        selected={teams}
        onChange={setTeams}
        legend={t.explore.teamsMulti}
        clearLabel={t.explore.clearTeams(teams.length)}
      />

      {error && <p className="status error">{t.explore.errLoad(error)}</p>}
      {!error && !rows && <p className="status">{t.explore.loading}</p>}
      {!error && rows && rows.length === 0 && (
        <p className="status">{t.explore.noStatData}</p>
      )}
      {!error && rows && rows.length > 0 && (
        <>
          <h2>{t.explore.rollingHeading(feature, windowLabel)}</h2>
          <FeatureChart
            data={series.data}
            teams={teams}
            yLabel={t.explore.chartYLabel(feature, rollWindow)}
          />
        </>
      )}
    </section>
  );
}
