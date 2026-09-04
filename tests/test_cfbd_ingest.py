"""Unit tests for hardened CFBD ingest (fake client only; no live API)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from pick_prophet.ingest.cfbd import CFBDClient, CFBDException, ingest_season
from pick_prophet.ingest.schemas import validate_endpoint_payload

FIXTURES = Path(__file__).parent / "fixtures" / "cfbd"


class FakeResponse:
    def __init__(self, payload: Any, *, code: int = 200) -> None:
        self._payload = payload
        self.code = code

    def read(self) -> bytes:
        if isinstance(self._payload, (bytes, bytearray)):
            return bytes(self._payload)
        return json.dumps(self._payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ScriptedClient(CFBDClient):
    """CFBDClient subclass that never hits the network."""

    def __init__(self, responses: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(api_key="test-key", sleep=lambda _: None, **kwargs)
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, params: dict[str, Any]) -> Any:  # type: ignore[override]
        self.calls.append((path, dict(params)))
        key = path
        if "week" in params:
            key = f"{path}?week={params['week']}"
        if key not in self.responses and path in self.responses:
            key = path
        value = self.responses[key]
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(path, params)
        return value


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _season_responses(season: int = 2025) -> dict[str, Any]:
    return {
        "/games": _load_fixture("games.json"),
        "/lines": _load_fixture("lines.json"),
        "/rankings": _load_fixture("rankings.json"),
        "/ratings/fpi": _load_fixture("fpi.json"),
        "/ratings/sp": _load_fixture("sp.json"),
        "/ratings/elo?week=1": _load_fixture("elo.json"),
        "/ratings/elo?week=2": [],
    }


def test_validate_endpoint_payload_accepts_fixtures() -> None:
    for name in ("games", "lines", "rankings", "fpi", "sp", "elo"):
        validate_endpoint_payload(name, _load_fixture(f"{name}.json"))


def test_validate_endpoint_payload_detects_drift() -> None:
    with pytest.raises(ValueError, match="schema drift"):
        validate_endpoint_payload("games", [{"season": 2025}])


def test_client_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    attempts = {"n": 0}

    def fake_urlopen(request, timeout=30):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,  # type: ignore[arg-type]
                fp=BytesIO(b"slow down"),
            )
        return FakeResponse([{"ok": True}])

    monkeypatch.setattr("pick_prophet.ingest.cfbd.urlopen", fake_urlopen)
    client = CFBDClient(api_key="k", sleep=sleeps.append, base_delay=0.01, max_attempts=4)
    assert client.get("/games", {"year": 2025}) == [{"ok": True}]
    assert attempts["n"] == 3
    assert sleeps == [0.01, 0.02]


def test_client_does_not_retry_401(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=30):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=BytesIO(b"nope"),
        )

    monkeypatch.setattr("pick_prophet.ingest.cfbd.urlopen", fake_urlopen)
    client = CFBDClient(api_key="k", sleep=lambda _: None, max_attempts=4)
    with pytest.raises(CFBDException, match="401"):
        client.get("/games", {"year": 2025})


def test_ingest_season_writes_manifest_and_files(tmp_path: Path) -> None:
    client = ScriptedClient(_season_responses())
    target = ingest_season(
        2025,
        tmp_path,
        max_week=2,
        weeks=[1, 2],
        client=client,
        snapshot="snap1",
    )
    assert (target / "games.json").exists()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["status"] == "complete"
    assert manifest["adapter_version"]
    assert manifest["request"]["weeks"] == [1, 2]
    assert "sha256" in manifest["files"]["games.json"]
    assert manifest["files"]["games.json"]["rows"] == 1
    elo_calls = [c for c in client.calls if c[0] == "/ratings/elo"]
    assert [c[1]["week"] for c in elo_calls] == [1, 2]


def test_ingest_resume_skips_completed_files(tmp_path: Path) -> None:
    client = ScriptedClient(_season_responses())
    target = ingest_season(
        2025, tmp_path, max_week=2, weeks=[1], client=client, snapshot="snap2"
    )
    games_before = (target / "games.json").read_text()
    # Remove elo so resume must refetch only that endpoint.
    (target / "elo.json").unlink()
    manifest = json.loads((target / "manifest.json").read_text())
    del manifest["files"]["elo.json"]
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    calls_before = len(client.calls)
    ingest_season(
        2025,
        tmp_path,
        max_week=2,
        weeks=[1],
        client=client,
        snapshot="snap2",
        resume=True,
    )
    assert (target / "games.json").read_text() == games_before
    # Should not re-fetch games/lines/rankings/fpi/sp — only elo weeks.
    new_paths = [c[0] for c in client.calls[calls_before:]]
    assert "/games" not in new_paths
    assert "/ratings/elo" in new_paths


def test_ingest_schema_failure_preserves_bad_payload(tmp_path: Path) -> None:
    responses = _season_responses()
    responses["/games"] = [{"season": 2025, "week": 1}]  # missing id
    client = ScriptedClient(responses)
    with pytest.raises(CFBDException, match="schema drift"):
        ingest_season(
            2025, tmp_path, max_week=1, weeks=[1], client=client, snapshot="bad"
        )
    bad = tmp_path / "cfbd" / "2025" / "bad" / "games.bad.json"
    assert bad.exists()
    assert not (tmp_path / "cfbd" / "2025" / "bad" / "games.json").exists()


def test_targeted_weeks_only_fetch_requested(tmp_path: Path) -> None:
    responses = _season_responses()
    responses["/ratings/elo?week=3"] = [{"team": "A", "elo": 1500}]
    client = ScriptedClient(responses)
    ingest_season(
        2025, tmp_path, max_week=20, weeks=[3], client=client, snapshot="w3"
    )
    elo_weeks = [c[1]["week"] for c in client.calls if c[0] == "/ratings/elo"]
    assert elo_weeks == [3]


def test_ingest_refuses_overwrite_without_resume(tmp_path: Path) -> None:
    client = ScriptedClient(_season_responses())
    target = ingest_season(
        2025, tmp_path, max_week=1, weeks=[1], client=client, snapshot="locked"
    )
    before = (target / "games.json").read_text()
    with pytest.raises(FileExistsError, match="snapshot already exists"):
        ingest_season(
            2025, tmp_path, max_week=1, weeks=[1], client=client, snapshot="locked"
        )
    assert (target / "games.json").read_text() == before
