"""Egress probe: can a cloud task pull FINAL SCORES without a residential IP?

Same pattern as the J.5 stats.nba.com diagnostic (docs/aws_deployment_plan.md):
hit each candidate source from inside a one-off Fargate task and distinguish
instant error vs full timeout vs success. Candidates:

    espn_scoreboard - site.api.espn.com scoreboard for a date (scores + status)
    espn_summary    - site.api.espn.com summary for one finished game (box score)
    cdn_scoreboard  - cdn.nba.com live todaysScoreboard (403s even from home as of
                      2026-10-22 — recorded for completeness only)
    stats_scoreboard- stats.nba.com scoreboardv3 (known AWS hard block; the
                      negative control — 200 from home, timeout from Fargate)

stats.nba.com fingerprints the client: plain urllib is dropped even from a
residential IP, so the nba.com calls go through `requests` with nba_api's
browser-like headers (what the working home ingest sends). Inlined into
infra/espn-probe-runtask.json as a `python -c` command override.

Usage (local, residential baseline):
    python scripts/egress_probe_scores.py [YYYYMMDD]
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
# nba_api's NBAStatsHTTP headers verbatim (UA/Sec-Ch-Ua values matter), minus Host (requests sets it per URL).
NBA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
               "Accept": "application/json, text/plain, */*",
               "Accept-Language": "en-US,en;q=0.5", "Accept-Encoding": "gzip, deflate, br",
               "Connection": "keep-alive", "Referer": "https://stats.nba.com/",
               "Pragma": "no-cache", "Cache-Control": "no-cache",
               "Sec-Ch-Ua": '"Chromium";v="140", "Google Chrome";v="140", "Not;A=Brand";v="24"',
               "Sec-Ch-Ua-Mobile": "?0", "Sec-Fetch-Dest": "empty"}

# Default: yesterday in US Eastern (UTC-5 is close enough for picking a slate date).
day = sys.argv[1] if len(sys.argv) > 1 else (datetime.now(timezone.utc) - timedelta(hours=5, days=1)).strftime("%Y%m%d")


def get(name, url, headers=None, timeout=20):
    t = time.time()
    try:
        if headers:  # nba.com: needs requests' client fingerprint, see docstring
            import requests
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            body, status = r.content, r.status_code
        else:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body, status = r.read(), r.status
        print(f"[{name}] HTTP {status} in {time.time() - t:.1f}s, {len(body)} bytes", flush=True)
        return json.loads(body)
    except Exception as e:
        print(f"[{name}] FAILED {type(e).__name__} after {time.time() - t:.1f}s: {str(e)[:140]}", flush=True)
        return None


print(f"probe slate date: {day}", flush=True)

sb = get("espn_scoreboard", f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={day}")
final_id = None
if sb:
    events = sb.get("events", [])
    print(f"  {len(events)} games", flush=True)
    for ev in events:
        comp = ev["competitions"][0]
        teams = {c["homeAway"]: f'{c["team"]["abbreviation"]} {c.get("score", "?")}' for c in comp["competitors"]}
        status = comp["status"]["type"]
        print(f'  {ev["id"]}: {teams.get("away")} @ {teams.get("home")}  [{status["name"]} completed={status["completed"]}]', flush=True)
        if status["completed"] and final_id is None:
            final_id = ev["id"]

if final_id:
    sm = get("espn_summary", f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={final_id}")
    if sm:
        teams = sm.get("boxscore", {}).get("players", [])
        for t in teams:
            stats = t["statistics"][0]
            print(f'  {t["team"]["abbreviation"]}: {len(stats["athletes"])} players, columns={stats["labels"]}', flush=True)

get("cdn_scoreboard", "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json", NBA_HEADERS)
iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
get("stats_scoreboard", f"https://stats.nba.com/stats/scoreboardv3?GameDate={iso}&LeagueID=00",
    {**NBA_HEADERS, "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}, timeout=30)
print("PROBE DONE", flush=True)
