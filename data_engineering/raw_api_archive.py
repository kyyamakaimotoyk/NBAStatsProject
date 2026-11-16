"""Raw nba_api response archive (home side).

Every response the ingest fetches is saved as received, before any column is
dropped or any frame is skipped. Nothing the API sends is lost when an endpoint
gains columns (nba_api 1.12.0 added two, 2026-11-16) or carries frames we don't
store yet. A column added to a table later is filled from this archive with
`data_engineering/backfill_from_raw.py`, with no second round of API calls.

Layout (one gzipped JSON file per endpoint call):
    <RAW_DIR>/<Endpoint>/<season>/<key>.json.gz
        Endpoint = nba_api class name (BoxScoreMiscV3, LeagueGameFinder, ...)
        season   = "2026-27" for game-keyed calls (from the game id), else a label
        key      = game id, or a date/stamp for league-wide calls
    File body: {"endpoint", "params", "fetched_at_utc", "nba_api", "url", "response"}
    where "response" is the raw response text, byte for byte.

RAW_DIR = $NBA_RAW_API_DIR, default <repo>/data/raw_api (git-ignored). Roughly
30-60 KB per game for all box-score endpoints; well under 1 GB a season.

Writing never raises: a full disk or a permission problem must not stop the
ingest. Failures are returned as False and logged by the caller.
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]


def raw_dir() -> Path:
    return Path(os.environ.get("NBA_RAW_API_DIR") or ROOT / "data" / "raw_api")


def season_of_game(game_id) -> str:
    """'0022600236' -> '2026-27' (digits 3-4 of the 10-digit id are the season year)."""
    gid = str(game_id).zfill(10)
    yy = int(gid[3:5])
    return f"20{yy:02d}-{(yy + 1) % 100:02d}"


def path_for(endpoint: str, season: str, key: str) -> Path:
    return raw_dir() / endpoint / season / f"{key}.json.gz"


def save_endpoint(ep, key: str, season: str | None = None) -> Path | None:
    """Archive a fetched nba_api endpoint object. key = game id or a label.
    Returns the path, or None if nothing was saved (never raises)."""
    try:
        import nba_api
        resp = getattr(ep, "nba_response", None)
        if resp is None:
            return None
        name = type(ep).__name__
        season = season or (season_of_game(key) if str(key).isdigit() else "misc")
        path = path_for(name, season, str(key))
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "endpoint": name,
            "params": getattr(ep, "parameters", {}),
            "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "nba_api": nba_api.__version__,
            "url": resp.get_url(),
            "response": resp.get_response(),
        }
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(body, f, default=str)
        os.replace(tmp, path)  # atomic: a crash never leaves a half-written file
        return path
    except Exception:  # noqa: BLE001 - archiving must never break the ingest
        return None


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def replay(endpoint_cls, body: dict, **init_kwargs):
    """Rebuild an endpoint object from an archived body, offline. init_kwargs are
    the constructor's required arguments (e.g. game_id=...)."""
    from nba_api.stats.library.http import NBAStatsResponse
    ep = endpoint_cls(get_request=False, **init_kwargs)
    ep.nba_response = NBAStatsResponse(response=body["response"], status_code=200,
                                       url=body.get("url", ""))
    ep.load_response()
    return ep


def iter_files(endpoint: str, season: str | None = None) -> Iterator[Path]:
    base = raw_dir() / endpoint
    if not base.exists():
        return iter(())
    pattern = f"{season}/*.json.gz" if season else "*/*.json.gz"
    return iter(sorted(base.glob(pattern)))


def inventory() -> dict:
    """{endpoint: {season: n_files}} for the report."""
    out: dict = {}
    base = raw_dir()
    if not base.exists():
        return out
    for ep_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for s_dir in sorted(p for p in ep_dir.iterdir() if p.is_dir()):
            n = sum(1 for _ in s_dir.glob("*.json.gz"))
            if n:
                out.setdefault(ep_dir.name, {})[s_dir.name] = n
    return out
