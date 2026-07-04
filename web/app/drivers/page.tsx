"use client";

import { useEffect, useMemo, useState } from "react";
import { getMarginCorrelations, type MarginCorrItem } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import MarginCorrChart from "@/components/MarginCorrChart";

export default function DriversPage() {
  const { t } = useLang();
  const [kind, setKind] = useState<"DIFF" | "HOME" | "AWAY">("DIFF");
  const [win, setWin] = useState<"L5" | "L10">("L5");
  const [topN, setTopN] = useState(20);
  const [all, setAll] = useState<MarginCorrItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAll(null);
    setError(null);
    getMarginCorrelations(kind, win)
      .then((r) => setAll(r.correlations))
      .catch((e) => setError(String(e)));
  }, [kind, win]);

  const top = useMemo(() => (all ? all.slice(0, topN) : []), [all, topN]);

  const summary = useMemo(() => {
    if (!all || all.length === 0) return null;
    const pos = [...all].sort((a, b) => b.correlation - a.correlation)[0];
    const neg = [...all].sort((a, b) => a.correlation - b.correlation)[0];
    return {
      pos,
      neg,
      n1: all.filter((i) => Math.abs(i.correlation) > 0.1).length,
      n2: all.filter((i) => Math.abs(i.correlation) > 0.2).length,
      total: all.length,
    };
  }, [all]);

  return (
    <section>
      <h1>{t.drivers.title}</h1>
      <p className="subtle">{t.drivers.subtitle}</p>

      <div className="controls explore-controls">
        <label>
          {t.drivers.sideLabel}{" "}
          <select value={kind} onChange={(e) => setKind(e.target.value as "DIFF" | "HOME" | "AWAY")}>
            <option value="DIFF">{t.drivers.sideDiff}</option>
            <option value="HOME">{t.drivers.sideHome}</option>
            <option value="AWAY">{t.drivers.sideAway}</option>
          </select>
        </label>
        <label>
          {t.drivers.windowLabel}{" "}
          <select value={win} onChange={(e) => setWin(e.target.value as "L5" | "L10")}>
            <option value="L5">{t.drivers.last5}</option>
            <option value="L10">{t.drivers.last10}</option>
          </select>
        </label>
        <label>
          {t.drivers.topLabel}{" "}
          <select value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
            {[10, 15, 20, 30, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="status error">{t.drivers.errLoad(error)}</p>}
      {!error && !all && <p className="status">{t.drivers.loading}</p>}
      {!error && all && all.length === 0 && (
        <p className="status">{t.drivers.noData}</p>
      )}
      {!error && all && all.length > 0 && (
        <>
          {summary && (
            <p className="subtle">
              {t.drivers.strongestPos} <strong>{summary.pos.feature}</strong> (
              {summary.pos.correlation.toFixed(3)}) · {t.drivers.strongestNeg}{" "}
              <strong>{summary.neg.feature}</strong> ({summary.neg.correlation.toFixed(3)}) ·{" "}
              {t.drivers.featureCounts(summary.n1, summary.n2, summary.total)}
            </p>
          )}
          <h2>{t.drivers.topHeading(top.length)}</h2>
          <MarginCorrChart items={top} />
        </>
      )}
    </section>
  );
}
