"use client";

import { useEffect, useRef, useState } from "react";
import { useLang } from "@/lib/i18n";
import type { FiveNum } from "@/lib/explore";
import ScatterPlot, { SCATTER_GEOM } from "@/components/ScatterPlot";

// Per-team five-number summaries for both axes (null = too few games to box).
export type TeamBox = {
  team: string;
  tricode: string;
  xW: FiveNum | null;
  xL: FiveNum | null;
  yW: FiveNum | null;
  yL: FiveNum | null;
};

type Pt = {
  x: number;
  y: number;
  team: string | null;
  date: string;
  home: string | null;
  away: string | null;
  winner: string | null;
};

type Hover = {
  tricode: string;
  wl: "W" | "L";
  color: string;
  axisLabel: string;
  stats: FiveNum;
  cx: number;
  cy: number;
};

const WIN = "#22c55e";
const LOSS = "#ef4444";
const INK_MUTED = "#9aa6c0";
const HAIRLINE = "#243049";
// One W row + one L row per team, in each strip.
const BOX_H = 9;
const SUB_H = 13;
const PAIR_H = SUB_H * 2 + 6;
const PAIR_W = SUB_H * 2 + 6;

const fmt = (v: number) => String(Math.round(v * 1000) / 1000);

/** Horizontal box-and-whisker: whisker min→max, box q1→q3, solid median. */
function HBox({
  s,
  cy,
  fx,
  color,
}: {
  s: FiveNum;
  cy: number;
  fx: (v: number) => number;
  color: string;
}) {
  return (
    <g>
      <line x1={fx(s.min)} x2={fx(s.max)} y1={cy} y2={cy} stroke={color} strokeWidth={1.5} opacity={0.6} />
      {[s.min, s.max].map((v, i) => (
        <line key={i} x1={fx(v)} x2={fx(v)} y1={cy - 3} y2={cy + 3} stroke={color} strokeWidth={1.5} opacity={0.6} />
      ))}
      <rect
        x={fx(s.q1)}
        y={cy - BOX_H / 2}
        width={Math.max(fx(s.q3) - fx(s.q1), 1)}
        height={BOX_H}
        rx={2}
        fill={color}
        fillOpacity={0.35}
      />
      <line x1={fx(s.med)} x2={fx(s.med)} y1={cy - BOX_H / 2 - 1} y2={cy + BOX_H / 2 + 1} stroke={color} strokeWidth={2} />
    </g>
  );
}

/** Vertical box-and-whisker (right strip). */
function VBox({
  s,
  cx,
  fy,
  color,
}: {
  s: FiveNum;
  cx: number;
  fy: (v: number) => number;
  color: string;
}) {
  return (
    <g>
      <line x1={cx} x2={cx} y1={fy(s.min)} y2={fy(s.max)} stroke={color} strokeWidth={1.5} opacity={0.6} />
      {[s.min, s.max].map((v, i) => (
        <line key={i} x1={cx - 3} x2={cx + 3} y1={fy(v)} y2={fy(v)} stroke={color} strokeWidth={1.5} opacity={0.6} />
      ))}
      <rect
        x={cx - BOX_H / 2}
        y={fy(s.q3)}
        width={BOX_H}
        height={Math.max(fy(s.q1) - fy(s.q3), 1)}
        rx={2}
        fill={color}
        fillOpacity={0.35}
      />
      <line x1={cx - BOX_H / 2 - 1} x2={cx + BOX_H / 2 + 1} y1={fy(s.med)} y2={fy(s.med)} stroke={color} strokeWidth={2} />
    </g>
  );
}

export default function ScatterWithMarginals({
  wins,
  losses,
  xLabel,
  yLabel,
  trend,
  xDomain,
  yDomain,
  boxes,
}: {
  wins: Pt[];
  losses: Pt[];
  xLabel: string;
  yLabel: string;
  trend: { x1: number; y1: number; x2: number; y2: number } | null;
  xDomain: [number, number];
  yDomain: [number, number];
  boxes: TeamBox[];
}) {
  const { t } = useLang();
  const wrapRef = useRef<HTMLDivElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const [topW, setTopW] = useState(0);
  const [hover, setHover] = useState<Hover | null>(null);

  const hasBoxes = boxes.length > 0;
  const rightW = hasBoxes ? boxes.length * PAIR_W + 8 : 0;

  // The top strip spans the chart column; measure it so value→px math is exact.
  useEffect(() => {
    const el = topRef.current;
    if (!el) return;
    const ro = new ResizeObserver((es) => setTopW(es[0].contentRect.width));
    ro.observe(el);
    setTopW(el.clientWidth);
    return () => ro.disconnect();
  }, [hasBoxes]);

  const move = (h: Omit<Hover, "cx" | "cy">) => (e: React.MouseEvent) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box) return;
    setHover({ ...h, cx: e.clientX - box.left, cy: e.clientY - box.top });
  };

  const topH = boxes.length * PAIR_H + 4;
  const innerW = Math.max(topW - SCATTER_GEOM.plotLeft - SCATTER_GEOM.plotRight, 1);
  const fx = (v: number) =>
    SCATTER_GEOM.plotLeft + ((v - xDomain[0]) / (xDomain[1] - xDomain[0])) * innerW;
  const plotH = SCATTER_GEOM.plotBottom - SCATTER_GEOM.plotTop;
  const fy = (v: number) =>
    SCATTER_GEOM.plotBottom - ((v - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotH;

  const wlWord = (wl: "W" | "L") => (wl === "W" ? t.scatter.win : t.scatter.loss);

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      {hasBoxes && (
        <div style={{ display: "flex" }}>
          <div ref={topRef} style={{ flex: 1, minWidth: 0 }}>
            <svg width="100%" height={topH} role="img" aria-label={`${xLabel} box plots`}>
              {boxes.map((b, i) => {
                const y0 = i * PAIR_H + 4;
                return (
                  <g key={b.team}>
                    <text
                      x={SCATTER_GEOM.plotLeft - 8}
                      y={y0 + SUB_H}
                      textAnchor="end"
                      fontSize={10}
                      fill={INK_MUTED}
                    >
                      {b.tricode}
                    </text>
                    {b.xW && <HBox s={b.xW} cy={y0 + SUB_H / 2} fx={fx} color={WIN} />}
                    {b.xL && <HBox s={b.xL} cy={y0 + SUB_H + 6 + SUB_H / 2} fx={fx} color={LOSS} />}
                    {(["W", "L"] as const).map((wl) => {
                      const s = wl === "W" ? b.xW : b.xL;
                      if (!s) return null;
                      const cy = wl === "W" ? y0 : y0 + SUB_H + 6;
                      return (
                        <rect
                          key={wl}
                          x={SCATTER_GEOM.plotLeft}
                          y={cy - 2}
                          width={innerW}
                          height={SUB_H + 4}
                          fill="transparent"
                          onMouseMove={move({
                            tricode: b.tricode,
                            wl,
                            color: wl === "W" ? WIN : LOSS,
                            axisLabel: xLabel,
                            stats: s,
                          })}
                          onMouseLeave={() => setHover(null)}
                        />
                      );
                    })}
                  </g>
                );
              })}
            </svg>
          </div>
          <div style={{ width: rightW, flexShrink: 0 }} />
        </div>
      )}

      <div style={{ display: "flex" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <ScatterPlot
            wins={wins}
            losses={losses}
            xLabel={xLabel}
            yLabel={yLabel}
            trend={trend}
            xDomain={xDomain}
            yDomain={yDomain}
          />
        </div>
        {hasBoxes && (
          <svg
            width={rightW}
            height={SCATTER_GEOM.height}
            style={{ flexShrink: 0 }}
            role="img"
            aria-label={`${yLabel} box plots`}
          >
            <line
              x1={0}
              x2={0}
              y1={SCATTER_GEOM.plotTop}
              y2={SCATTER_GEOM.plotBottom}
              stroke={HAIRLINE}
              strokeWidth={1}
            />
            {boxes.map((b, i) => {
              const x0 = i * PAIR_W + 8;
              return (
                <g key={b.team}>
                  <text
                    x={x0 + PAIR_W / 2}
                    y={SCATTER_GEOM.plotTop - 6}
                    textAnchor="middle"
                    fontSize={10}
                    fill={INK_MUTED}
                  >
                    {b.tricode}
                  </text>
                  {b.yW && <VBox s={b.yW} cx={x0 + SUB_H / 2} fy={fy} color={WIN} />}
                  {b.yL && <VBox s={b.yL} cx={x0 + SUB_H + 6 + SUB_H / 2} fy={fy} color={LOSS} />}
                  {(["W", "L"] as const).map((wl) => {
                    const s = wl === "W" ? b.yW : b.yL;
                    if (!s) return null;
                    const cx = wl === "W" ? x0 : x0 + SUB_H + 6;
                    return (
                      <rect
                        key={wl}
                        x={cx - 2}
                        y={SCATTER_GEOM.plotTop}
                        width={SUB_H + 4}
                        height={plotH}
                        fill="transparent"
                        onMouseMove={move({
                          tricode: b.tricode,
                          wl,
                          color: wl === "W" ? WIN : LOSS,
                          axisLabel: yLabel,
                          stats: s,
                        })}
                        onMouseLeave={() => setHover(null)}
                      />
                    );
                  })}
                </g>
              );
            })}
          </svg>
        )}
      </div>

      {hover && (
        <div
          className="box-tip"
          style={{
            left: Math.min(hover.cx + 14, Math.max((wrapRef.current?.clientWidth ?? 300) - 170, 0)),
            top: hover.cy + 14,
          }}
        >
          <div className="box-tip-title">
            <span className="box-tip-key" style={{ background: hover.color }} />
            {hover.tricode} · {wlWord(hover.wl)} — {hover.axisLabel}
          </div>
          {(
            [
              [hover.stats.max, t.scatter.box.max],
              [hover.stats.q3, t.scatter.box.q3],
              [hover.stats.med, t.scatter.box.median],
              [hover.stats.q1, t.scatter.box.q1],
              [hover.stats.min, t.scatter.box.min],
            ] as [number, string][]
          ).map(([v, label]) => (
            <div key={label} className="box-tip-row">
              <strong>{fmt(v)}</strong> <span>{label}</span>
            </div>
          ))}
          <div className="box-tip-n">{t.scatter.box.gamesLabel(hover.stats.n)}</div>
        </div>
      )}
    </div>
  );
}
