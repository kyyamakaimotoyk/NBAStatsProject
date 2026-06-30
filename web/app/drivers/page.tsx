"use client";

import { useEffect, useMemo, useState } from "react";
import { getMarginCorrelations, type MarginCorrItem } from "@/lib/api";
import MarginCorrChart from "@/components/MarginCorrChart";

export default function DriversPage() {
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
      <h1>What drives winning</h1>
      <p className="subtle">
        How strongly each rolling team stat correlates with a game&apos;s final margin.
        Positive = more of it tends to go with winning.
      </p>

      <div className="controls explore-controls">
        <label>
          Side:{" "}
          <select value={kind} onChange={(e) => setKind(e.target.value as "DIFF" | "HOME" | "AWAY")}>
            <option value="DIFF">Differential (home − away)</option>
            <option value="HOME">Home team</option>
            <option value="AWAY">Away team</option>
          </select>
        </label>
        <label>
          Window:{" "}
          <select value={win} onChange={(e) => setWin(e.target.value as "L5" | "L10")}>
            <option value="L5">Last 5</option>
            <option value="L10">Last 10</option>
          </select>
        </label>
        <label>
          Top:{" "}
          <select value={topN} onChange={(e) => setTopN(Number(e.target.value))}>
            {[10, 15, 20, 30, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="status error">Couldn&apos;t load: {error}</p>}
      {!error && !all && <p className="status">Loading…</p>}
      {!error && all && all.length === 0 && (
        <p className="status">No correlation data available.</p>
      )}
      {!error && all && all.length > 0 && (
        <>
          {summary && (
            <p className="subtle">
              Strongest positive: <strong>{summary.pos.feature}</strong> (
              {summary.pos.correlation.toFixed(3)}) · strongest negative:{" "}
              <strong>{summary.neg.feature}</strong> ({summary.neg.correlation.toFixed(3)}) ·{" "}
              {summary.n1} features with |r| &gt; 0.1, {summary.n2} with |r| &gt; 0.2 (of{" "}
              {summary.total}).
            </p>
          )}
          <h2>Top {top.length} by |correlation| with margin</h2>
          <MarginCorrChart items={top} />
        </>
      )}
    </section>
  );
}
