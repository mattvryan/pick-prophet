"""Small dependency-free client that persists immutable CFBD responses."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.collegefootballdata.com"


class CFBDException(RuntimeError):
    """A contextual error returned by the CFBD client."""


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    weekly: bool = False


ENDPOINTS = (
    Endpoint("games", "/games"),
    Endpoint("lines", "/lines"),
    Endpoint("rankings", "/rankings"),
    # CFBD currently exposes only season-level FPI/SP+ through these endpoints.
    # Preserve them as raw research inputs, but do not pretend they are weekly.
    Endpoint("fpi", "/ratings/fpi"),
    Endpoint("sp", "/ratings/sp"),
    Endpoint("elo", "/ratings/elo", weekly=True),
)


class CFBDClient:
    def __init__(self, api_key: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.environ.get("CFBD_API_KEY")
        if not self.api_key:
            raise CFBDException("CFBD_API_KEY is required; see .env.example")
        self.timeout = timeout

    def get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{BASE_URL}{path}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "pick-prophet/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise CFBDException(f"CFBD {exc.code} for {path}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise CFBDException(f"CFBD request failed for {path}: {exc}") from exc


def ingest_season(
    season: int,
    raw_root: Path,
    *,
    max_week: int = 20,
    client: CFBDClient | None = None,
    snapshot: str | None = None,
) -> Path:
    """Download one season into a unique snapshot directory."""
    client = client or CFBDClient()
    snapshot = snapshot or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = raw_root / "cfbd" / str(season) / snapshot
    if target.exists():
        raise FileExistsError(f"snapshot already exists: {target}")
    target.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "source": BASE_URL,
        "season": season,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }
    for endpoint in ENDPOINTS:
        if endpoint.weekly:
            payload = []
            for week in range(1, max_week + 1):
                rows = client.get(
                    endpoint.path,
                    {"year": season, "week": week, "seasonType": "both"},
                )
                for row in rows:
                    row.setdefault("week", week)
                payload.extend(rows)
        else:
            payload = client.get(endpoint.path, {"year": season})
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode()
        filename = f"{endpoint.name}.json"
        (target / filename).write_bytes(encoded)
        manifest["files"][filename] = {
            "rows": len(payload),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        time.sleep(0.05)
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return target
