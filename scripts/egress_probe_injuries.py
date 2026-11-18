"""Egress probe: can a cloud task fetch the NBA's official injury-report PDFs?

The injury scraper (historical_injury_scraper.py) runs at home because every
nba.com host was ASSUMED to block datacenter IPs. That was only ever measured for
stats.nba.com (hard block) and cdn.nba.com (403, even from home since 2026-06).
The PDFs live on ak-static.cms.nba.com, which answers as plain `Server: AmazonS3`
with no browser headers needed (checked from home 2026-11-18). This probe settles
it from inside a one-off Fargate task, same pattern as egress_probe_scores.py:

    pdf_<slot>   - GET a report PDF for yesterday's ET slate (5:00 PM and 7:30 PM
                   slots). Success = HTTP 200 + a %PDF body.
    stats_ctrl   - stats.nba.com scoreboardv3, the known AWS block (negative
                   control: expect a timeout from Fargate; it also drops plain
                   urllib from home, so only its Fargate result means anything).
    java         - is a JRE on PATH? (the parser, tabula-py, needs one; the
                   current pipeline image has none, so "missing" is expected)

Stdlib only, so it runs in the current image as a `python -c` override (see
infra/injury-probe-runtask.json, generated from this file).

Usage (local, residential baseline):
    python scripts/egress_probe_injuries.py [YYYY-MM-DD]
"""
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
day = sys.argv[1] if len(sys.argv) > 1 else (datetime.now(timezone.utc) - timedelta(hours=5, days=1)).strftime("%Y-%m-%d")


def get(name, url, headers=None, timeout=20):
    t = time.time()
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            print(f"[{name}] HTTP {r.status} in {time.time() - t:.1f}s, {len(body)} bytes, "
                  f"pdf={body[:4] == b'%PDF'}, server={r.headers.get('Server')}", flush=True)
    except Exception as e:
        print(f"[{name}] FAILED {type(e).__name__} after {time.time() - t:.1f}s: {str(e)[:140]}", flush=True)


print(f"probe date (ET slate): {day}", flush=True)
for slot in ("05_00PM", "07_30PM"):
    get(f"pdf_{slot}", f"https://ak-static.cms.nba.com/referee/injury/Injury-Report_{day}_{slot}.pdf")
get("stats_ctrl", f"https://stats.nba.com/stats/scoreboardv3?GameDate={day}&LeagueID=00",
    {"User-Agent": UA, "Referer": "https://stats.nba.com/", "Accept": "application/json"}, timeout=30)
print(f"[java] {shutil.which('java') or 'missing'}", flush=True)
