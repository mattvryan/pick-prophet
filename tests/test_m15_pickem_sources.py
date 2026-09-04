from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pick_prophet.research.m15_pickem_sources import (
    load_and_validate,
    validate_source_inventory,
)


def test_committed_inventory_validates_without_confirming_candidates() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = load_and_validate(
        root / "docs/modeling_artifacts/m15/1.0.0/source_inventory.json"
    )
    assert payload["confirmed_historical_weeks_added"] == 0
    assert {row["status"] for row in payload["week_candidates"]} == {
        "candidate_single_source"
    }
    manifest = json.loads(
        (root / "docs/modeling_artifacts/m15/1.0.0/manifest.json").read_text()
    )
    inventory = root / "docs/modeling_artifacts/m15/1.0.0/source_inventory.json"
    assert (
        hashlib.sha256(inventory.read_bytes()).hexdigest()
        == manifest["artifacts_sha256"]["source_inventory.json"]
    )


def test_single_source_cannot_be_confirmed() -> None:
    payload = {
        "artifact_version": "1.0.0",
        "week_candidates": [
            {
                "season": 2024,
                "week": 3,
                "status": "confirmed",
                "sources": [{"source_id": "one"}],
                "pre_lock_provenance_verified": True,
                "canonical_game_ids_verified": 10,
            }
        ],
    }
    with pytest.raises(ValueError, match="requires two sources"):
        validate_source_inventory(payload)


def test_confirmation_requires_prelock_and_game_ids() -> None:
    base = {
        "artifact_version": "1.0.0",
        "week_candidates": [
            {
                "season": 2024,
                "week": 3,
                "status": "confirmed",
                "sources": [{"source_id": "one"}, {"source_id": "two"}],
                "pre_lock_provenance_verified": False,
                "canonical_game_ids_verified": 10,
            }
        ],
    }
    with pytest.raises(ValueError, match="pre-lock"):
        validate_source_inventory(base)
    base["week_candidates"][0]["pre_lock_provenance_verified"] = True
    base["week_candidates"][0]["canonical_game_ids_verified"] = 0
    with pytest.raises(ValueError, match="canonical game IDs"):
        validate_source_inventory(base)


def test_duplicate_week_and_source_ids_fail() -> None:
    path = Path("docs/modeling_artifacts/m15/1.0.0/source_inventory.json")
    payload = json.loads(path.read_text())
    payload["week_candidates"].append(dict(payload["week_candidates"][0]))
    with pytest.raises(ValueError, match="duplicate season/week"):
        validate_source_inventory(payload)
