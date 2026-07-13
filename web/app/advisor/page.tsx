"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getAdvice, type AdvisorResponse } from "@/lib/api";
import { useLang } from "@/lib/i18n";

// Cloudflare Turnstile (bot friction). Empty sitekey = widget disabled and no
// token is sent; the backend only enforces verification when its secret is
// configured, so the two flags flip together at deploy time.
const TURNSTILE_SITEKEY = process.env.NEXT_PUBLIC_TURNSTILE_SITEKEY ?? "";

type TurnstileAPI = {
  render: (
    el: HTMLElement,
    opts: {
      sitekey: string;
      callback: (token: string) => void;
      "expired-callback"?: () => void;
    },
  ) => string;
  reset: (widgetId?: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileAPI;
  }
}

export default function AdvisorPage() {
  const { t } = useLang();
  const [prompt, setPrompt] = useState("");
  const [roster, setRoster] = useState("");
  const [matchup, setMatchup] = useState("");
  const [scoring, setScoring] = useState<"points" | "category">("points");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AdvisorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);

  useEffect(() => {
    if (!TURNSTILE_SITEKEY) return;
    const render = () => {
      if (widgetRef.current && window.turnstile && widgetId.current === null) {
        widgetId.current = window.turnstile.render(widgetRef.current, {
          sitekey: TURNSTILE_SITEKEY,
          callback: (token) => setCaptchaToken(token),
          "expired-callback": () => setCaptchaToken(null),
        });
      }
    };
    if (window.turnstile) {
      render();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = render;
    document.head.appendChild(script);
  }, []);

  const submit = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await getAdvice({
          prompt: prompt.trim(),
          roster: roster.trim() || undefined,
          matchup_score: matchup.trim() || undefined,
          scoring_type: scoring,
          turnstile_token: captchaToken ?? undefined,
        }),
      );
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      // Turnstile tokens are single-use: reset so the next submit gets a fresh one.
      if (TURNSTILE_SITEKEY && window.turnstile && widgetId.current !== null) {
        window.turnstile.reset(widgetId.current);
        setCaptchaToken(null);
      }
      setBusy(false);
    }
  };

  const captchaPending = Boolean(TURNSTILE_SITEKEY) && captchaToken === null;

  return (
    <section>
      <h1>{t.advisor.title}</h1>
      <p className="subtle">
        {t.advisor.subtitle} <Link href="/players">{t.advisor.tableLink}</Link>
      </p>

      <div className="advisor-form">
        <label>
          {t.advisor.promptLabel}
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder={t.advisor.promptPlaceholder}
          />
        </label>
        <label>
          {t.advisor.rosterLabel}
          <textarea
            value={roster}
            onChange={(e) => setRoster(e.target.value)}
            maxLength={2500}
            rows={3}
            placeholder={t.advisor.rosterPlaceholder}
          />
        </label>
        <div className="controls explore-controls">
          <label>
            {t.advisor.matchupLabel}{" "}
            <input
              type="text"
              value={matchup}
              onChange={(e) => setMatchup(e.target.value)}
              maxLength={500}
              placeholder={t.advisor.matchupPlaceholder}
            />
          </label>
          <label>
            {t.advisor.scoringLabel}{" "}
            <select
              value={scoring}
              onChange={(e) => setScoring(e.target.value as "points" | "category")}
            >
              <option value="points">{t.advisor.scoringPoints}</option>
              <option value="category">{t.advisor.scoringCategory}</option>
            </select>
          </label>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !prompt.trim() || captchaPending}
          >
            {busy ? t.advisor.thinking : t.advisor.submit}
          </button>
        </div>
        <div ref={widgetRef} />
      </div>

      {error && <p className="status error">{t.advisor.errLoad(error)}</p>}
      {busy && <p className="status">{t.advisor.thinking}</p>}
      {result && (
        <>
          <h2>{t.advisor.answerHeading(result.slate_date ?? "—")}</h2>
          {/* Model output is untrusted: rendered as plain text only. */}
          <div className="advisor-answer">
            {result.advice.split(/\n{2,}/).map((para, i) => (
              <p key={i} style={{ whiteSpace: "pre-wrap" }}>
                {para}
              </p>
            ))}
          </div>
        </>
      )}
      <p className="caption">{t.advisor.disclaimer}</p>
    </section>
  );
}
