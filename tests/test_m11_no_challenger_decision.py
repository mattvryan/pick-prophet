"""M11 not-run decision: blocked by empty M10 promoted feature set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pick_prophet.models.approved_feature_set import (
    EmptyPromotedFeaturesError,
    require_promoted_features_for_m11,
)
from pick_prophet.models.m11_decision import (
    IneligibleM11FeaturesError,
    M10ArtifactHashMismatchError,
    build_m11_feature_set,
    load_m11_decision,
    record_no_challenger_decision,
    resolve_m11_feature_set_for_run,
    sha256_file,
    validate_m10_approved_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
M10_APPROVED = ROOT / "docs" / "modeling_artifacts" / "m10" / "1.0.0" / "approved_feature_set.json"
M11_DECISION = ROOT / "docs" / "modeling_artifacts" / "m11" / "1.0.0" / "decision.json"
M11_ARTIFACT_DIR = M11_DECISION.parent
FORBIDDEN_ARTIFACT_GLOBS = (
    "**/bundle_*.json",
    "**/predictions*.csv",
    "**/model*.pkl",
    "**/model*.joblib",
    "**/*fitted*",
)


def test_tracked_m11_decision_matches_m10_artifact_hash() -> None:
    decision = load_m11_decision(M11_DECISION)
    expected = sha256_file(M10_APPROVED)
    assert decision["m10_approved_feature_set_path"] == (
        "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json"
    )
    assert decision["m10_approved_feature_set_sha256"] == expected
    assert decision["status"] == "not_run_no_promoted_features"
    assert decision["challenger_trained"] is False
    assert decision["baseline_retained"] == "market_only"
    assert decision["promoted_features"] == []


def test_validate_m10_approved_artifact_rejects_hash_mismatch(
    tmp_path: Path,
) -> None:
    approved = json.loads(M10_APPROVED.read_text())
    with pytest.raises(M10ArtifactHashMismatchError):
        validate_m10_approved_artifact(
            M10_APPROVED,
            expected_sha256="0" * 64,
            approved=approved,
        )


def test_record_no_challenger_decision_validates_hash_before_write(
    tmp_path: Path,
) -> None:
    out = tmp_path / "decision.json"
    approved = json.loads(M10_APPROVED.read_text())
    digest = sha256_file(M10_APPROVED)

    with pytest.raises(M10ArtifactHashMismatchError):
        record_no_challenger_decision(
            m10_approved_path=M10_APPROVED,
            expected_sha256="deadbeef" * 8,
            out_path=out,
            reviewer="Matt Ryan",
            reviewed_at_utc="2026-09-04T21:30:00Z",
        )
    assert not out.exists()

    payload = record_no_challenger_decision(
        m10_approved_path=M10_APPROVED,
        expected_sha256=digest,
        out_path=out,
        reviewer="Matt Ryan",
        reviewed_at_utc="2026-09-04T21:30:00Z",
    )
    assert out.exists()
    assert payload["m10_approved_feature_set_sha256"] == digest
    assert payload["challenger_trained"] is False
    assert approved["promoted_features"] == []


def test_no_model_bundle_or_prediction_artifacts_under_m11() -> None:
    assert M11_ARTIFACT_DIR.is_dir()
    found: list[Path] = []
    for pattern in FORBIDDEN_ARTIFACT_GLOBS:
        found.extend(M11_ARTIFACT_DIR.glob(pattern))
    assert found == [], f"unexpected M11 model/prediction artifacts: {found}"
    # Only the decision artifact is expected in this versioned pack.
    tracked = sorted(p.name for p in M11_ARTIFACT_DIR.iterdir() if p.is_file())
    assert tracked == ["decision.json"]


def test_review_only_and_rejected_cannot_enter_m11_feature_set() -> None:
    approved = json.loads(M10_APPROVED.read_text())
    with pytest.raises(IneligibleM11FeaturesError, match="review_only"):
        build_m11_feature_set(approved, candidate_features=["home_sos"])
    with pytest.raises(IneligibleM11FeaturesError, match="rejected"):
        build_m11_feature_set(
            approved,
            candidate_features=["line_provider_count"],
        )
    with pytest.raises(IneligibleM11FeaturesError):
        build_m11_feature_set(
            approved,
            candidate_features=["home_sos", "spread_home"],
        )
    # Empty promote set is the only legal set for this artifact.
    assert build_m11_feature_set(approved, candidate_features=[]) == []


def test_future_m11_run_fail_closed_until_explicit_promotion() -> None:
    decision = load_m11_decision(M11_DECISION)
    approved = validate_m10_approved_artifact(
        M10_APPROVED,
        expected_sha256=decision["m10_approved_feature_set_sha256"],
    )
    with pytest.raises(EmptyPromotedFeaturesError, match="fail closed"):
        require_promoted_features_for_m11(approved)
    with pytest.raises(EmptyPromotedFeaturesError):
        resolve_m11_feature_set_for_run(approved)
    # Explicit baseline-only remains opt-in and still trains nothing here.
    assert require_promoted_features_for_m11(
        approved,
        allow_baseline_only=True,
    ) == []
