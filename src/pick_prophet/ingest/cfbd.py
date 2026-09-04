"""Small dependency-free client that persists immutable CFBD responses."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .schemas import validate_endpoint_payload

BASE_URL = "https://api.collegefootballdata.com"
ADAPTER_VERSION = "1.1.0"

# Retry only transient failures. Auth and missing routes fail immediately.
_RETRYABLE_HTTP = frozenset({429, 500, 502, 503, 504})
_DEFAULT_MAX_ATTEMPTS = 4
_DEFAULT_BASE_DELAY = 0.5


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
    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
        *,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        base_delay: float = _DEFAULT_BASE_DELAY,
        sleep: Any = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ.get("CFBD_API_KEY")
        if not self.api_key:
            raise CFBDException("CFBD_API_KEY is required; see .env.example")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self._sleep = sleep

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
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code not in _RETRYABLE_HTTP or attempt >= self.max_attempts:
                    raise CFBDException(f"CFBD {exc.code} for {path}: {detail}") from exc
                last_error = CFBDException(f"CFBD {exc.code} for {path}: {detail}")
            except (URLError, TimeoutError) as exc:
                if attempt >= self.max_attempts:
                    raise CFBDException(f"CFBD request failed for {path}: {exc}") from exc
                last_error = CFBDException(f"CFBD request failed for {path}: {exc}")
            delay = self.base_delay * (2 ** (attempt - 1))
            self._sleep(delay)
        assert last_error is not None
        raise last_error


def _file_complete(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _write_payload(path: Path, payload: Any) -> dict[str, Any]:
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode()
    path.write_bytes(encoded)
    return {
        "rows": len(payload) if isinstance(payload, list) else None,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
        "written_at": datetime.now(UTC).isoformat(),
    }


def _persist_bad_payload(target: Path, filename: str, payload: Any) -> Path:
    bad_path = target / f"{Path(filename).stem}.bad.json"
    bad_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return bad_path


def _resolve_weeks(max_week: int, weeks: list[int] | None) -> list[int]:
    if weeks is None:
        return list(range(1, max_week + 1))
    cleaned = sorted({int(w) for w in weeks if int(w) >= 1})
    if not cleaned:
        raise ValueError("--weeks must include at least one positive week number")
    return cleaned


def ingest_season(
    season: int,
    raw_root: Path,
    *,
    max_week: int = 20,
    weeks: list[int] | None = None,
    client: CFBDClient | None = None,
    snapshot: str | None = None,
    resume: bool = False,
) -> Path:
    """Download one season into a unique snapshot directory.

    When ``resume`` is true and ``snapshot`` points at an existing directory,
    completed endpoint files are left untouched. Incomplete or missing files
    are fetched. Schema drift preserves the bad payload as ``*.bad.json`` and
    fails the run without overwriting a prior good file.
    """
    client = client or CFBDClient()
    week_list = _resolve_weeks(max_week, weeks)
    if resume:
        if not snapshot:
            raise ValueError("resume requires an explicit --snapshot directory name")
        target = raw_root / "cfbd" / str(season) / snapshot
        if not target.exists():
            raise FileNotFoundError(f"snapshot to resume does not exist: {target}")
    else:
        snapshot = snapshot or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = raw_root / "cfbd" / str(season) / snapshot
        if target.exists():
            raise FileExistsError(f"snapshot already exists: {target}")
        target.mkdir(parents=True)

    manifest_path = target / "manifest.json"
    if resume and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {
            "source": BASE_URL,
            "season": season,
            "adapter_version": ADAPTER_VERSION,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "request": {
                "max_week": max_week,
                "weeks": week_list,
                "resume": resume,
            },
            "status": "in_progress",
            "files": {},
        }

    manifest["adapter_version"] = ADAPTER_VERSION
    manifest["request"] = {
        "max_week": max_week,
        "weeks": week_list,
        "resume": resume,
    }
    errors: list[str] = []

    for endpoint in ENDPOINTS:
        filename = f"{endpoint.name}.json"
        out_path = target / filename
        if resume and _file_complete(out_path):
            # Keep existing file metadata; refresh only if missing.
            if filename not in manifest.get("files", {}):
                encoded = out_path.read_bytes()
                payload = json.loads(encoded)
                manifest.setdefault("files", {})[filename] = {
                    "rows": len(payload) if isinstance(payload, list) else None,
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "bytes": len(encoded),
                    "written_at": datetime.fromtimestamp(
                        out_path.stat().st_mtime, tz=UTC
                    ).isoformat(),
                    "resumed": True,
                }
            continue

        payload: Any = None
        try:
            if endpoint.weekly:
                payload = []
                for week in week_list:
                    rows = client.get(
                        endpoint.path,
                        {"year": season, "week": week, "seasonType": "both"},
                    )
                    if not isinstance(rows, list):
                        raise TypeError(
                            f"CFBD {endpoint.name} week {week}: expected array"
                        )
                    for row in rows:
                        if isinstance(row, dict):
                            row.setdefault("week", week)
                    payload.extend(rows)
            else:
                payload = client.get(endpoint.path, {"year": season})

            validate_endpoint_payload(endpoint.name, payload)
            meta = _write_payload(out_path, payload)
            meta["params"] = (
                {"year": season, "weeks": week_list, "seasonType": "both"}
                if endpoint.weekly
                else {"year": season}
            )
            manifest.setdefault("files", {})[filename] = meta
        except Exception as exc:
            if payload is not None:
                bad = _persist_bad_payload(target, filename, payload)
                errors.append(f"{endpoint.name}: {exc} (preserved {bad.name})")
            else:
                errors.append(f"{endpoint.name}: {exc}")
            manifest["status"] = "failed"
            manifest["errors"] = errors
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            )
            raise CFBDException("; ".join(errors)) from exc
        time.sleep(0.05)

    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return target
