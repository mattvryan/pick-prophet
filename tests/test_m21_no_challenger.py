from __future__ import annotations

import json
from pathlib import Path

import pytest

from pick_prophet.features.matrix_v2 import M20_CANDIDATE_COLUMNS
from pick_prophet.models.m21_decision import (
    M20DecisionHashMismatchError,
    record_m21_no_challenger,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
APPROVED = (
    ROOT
    / "docs"
    / "modeling_artifacts"
    / "m20"
    / "2.0.0"
    / "approved_feature_set.json"
)
DECISION_DIR = ROOT / "docs" / "modeling_artifacts" / "m21" / "2.0.0"


def test_tracked_decision_matches_human_approved_m20_hash() -> None:
    decision = json.loads((DECISION_DIR / "decision.json").read_text())
    assert decision["m20_approved_feature_set_sha256"] == sha256_file(APPROVED)
    assert decision["status"] == "complete_no_challenger"
    assert decision["challenger_trained"] is False
    assert decision["baseline_retained"] == "market_only"
    assert decision["registry_changed"] is False


def test_human_disposition_rejects_every_m20_candidate() -> None:
    approved = json.loads(APPROVED.read_text())
    assert approved["reviewer"] == "Matt Ryan"
    assert approved["human_decision"] == "no_features_promoted"
    assert approved["promoted_features"] == []
    assert set(approved["rejected_features"]) == set(M20_CANDIDATE_COLUMNS)
    assert sha256_file(ROOT / approved["decision_packet_path"]) == approved[
        "decision_packet_sha256"
    ]
    assert sha256_file(ROOT / approved["evidence_manifest_path"]) == approved[
        "evidence_manifest_sha256"
    ]


def test_recorder_fails_closed_on_hash_or_features(tmp_path: Path) -> None:
    output = tmp_path / "decision.json"
    with pytest.raises(M20DecisionHashMismatchError):
        record_m21_no_challenger(
            approved_path=APPROVED,
            expected_sha256="0" * 64,
            output_path=output,
            reviewer="Matt Ryan",
            reviewed_at_utc="2026-09-05T00:31:15Z",
        )
    assert not output.exists()

    modified = json.loads(APPROVED.read_text())
    modified["promoted_features"] = ["not_allowed"]
    path = tmp_path / "modified.json"
    path.write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="empty promoted"):
        record_m21_no_challenger(
            approved_path=path,
            expected_sha256=sha256_file(path),
            output_path=output,
            reviewer="Matt Ryan",
            reviewed_at_utc="2026-09-05T00:31:15Z",
        )


def test_no_fitted_artifacts_are_committed_under_m21() -> None:
    assert sorted(path.name for path in DECISION_DIR.iterdir()) == ["decision.json"]
