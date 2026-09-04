"""M12 registry acceptance tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pick_prophet.registry.bootstrap import bootstrap_m12_v1
from pick_prophet.registry.evaluate import CandidatePackage, evaluate_candidate
from pick_prophet.registry.hashing import sha256_file
from pick_prophet.registry.paths import UnsafeRegistryPathError, normalize_repo_path
from pick_prophet.registry.records import build_registry_entry
from pick_prophet.registry.store import (
    ImmutableRecordError,
    RegistryStore,
    StaleTipError,
)
from pick_prophet.registry.transitions import (
    approve,
    designate_shadow,
    register_candidate,
    retire,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "modeling_artifacts" / "m12" / "1.0.0"


@pytest.fixture()
def repo_tmp(tmp_path: Path) -> Path:
    """Minimal repo mirror with M10/M11 artifacts + bootstrap pack."""
    for rel in (
        "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json",
        "docs/modeling_artifacts/m11/1.0.0/decision.json",
    ):
        src = ROOT / rel
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    bootstrap_m12_v1(
        repo_root=tmp_path,
        reviewer="Matt Ryan",
        reviewed_at_utc="2026-09-04T21:38:29Z",
    )
    return tmp_path


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return sha256_file(path)


def _promoted_m10(repo: Path, features: list[str]) -> tuple[str, str]:
    src = json.loads(
        (repo / "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json").read_text()
    )
    src["promoted_features"] = features
    src["status"] = "features_promoted" if features else "no_features_promoted"
    # drop hash fields that would be stale; not required by loader
    rel = "docs/modeling_artifacts/m10/1.0.0/approved_feature_set_promoted.json"
    path = repo / rel
    digest = _write(path, json.dumps(src, sort_keys=True) + "\n")
    return rel, digest


def _passing_package(
    repo: Path,
    *,
    features: list[str],
    m10_rel: str,
    m10_sha: str,
    unequal_ids: bool = False,
    include_review_only: bool = False,
) -> CandidatePackage:
    if include_review_only:
        features = [*features, "home_sos"]
    bundle_rel = "artifacts/m12_test/bundle.json"
    cand_pred = "artifacts/m12_test/candidate_preds.csv"
    base_pred = "artifacts/m12_test/baseline_preds.csv"
    bundle_sha = _write(repo / bundle_rel, '{"ok":true}\n')
    cand_sha = _write(repo / cand_pred, "game_id,p\n1,0.6\n2,0.55\n")
    base_sha = _write(repo / base_pred, "game_id,p\n1,0.5\n2,0.5\n")
    ids_c = list(range(1, 121))
    ids_b = list(range(1, 121))
    if unequal_ids:
        ids_b = list(range(2, 122))
    seasons = [2022, 2023, 2024]
    per = {2022: 40, 2023: 40, 2024: 40}
    return CandidatePackage(
        protocol_version="1.0.0",
        matrix_schema_version="1.0.0",
        feature_set=features,
        m10_approved_feature_set_path=m10_rel,
        m10_approved_feature_set_sha256=m10_sha,
        bundle_path=bundle_rel,
        bundle_sha256=bundle_sha,
        candidate_predictions_path=cand_pred,
        candidate_predictions_sha256=cand_sha,
        baseline_predictions_path=base_pred,
        baseline_predictions_sha256=base_sha,
        paired_game_ids_candidate=ids_c,
        paired_game_ids_baseline=ids_b,
        seasons=seasons,
        games_per_season=per,
        aggregate_log_loss_candidate=0.60,
        aggregate_log_loss_baseline=0.62,
        aggregate_brier_candidate=0.20,
        aggregate_brier_baseline=0.22,
        log_loss_ci_low=-0.03,
        log_loss_ci_high=-0.01,
        brier_ci_low=-0.03,
        brier_ci_high=-0.01,
        per_season_delta_log_loss={2022: -0.01, 2023: -0.02, 2024: -0.01},
        per_season_delta_brier={2022: -0.01, 2023: -0.02, 2024: -0.01},
        calibration_candidate=0.04,
        calibration_baseline=0.04,
        prediction_coverage=0.99,
        timing_classification="pre_lock",
        leakage_status="clear",
    )


def test_committed_pack_validates_market_only_without_bundle() -> None:
    store = RegistryStore(root=PACK, repo_root=ROOT)
    store.validate()
    rows = store.list_models()
    assert len(rows) == 1
    assert rows[0]["model_id"] == "market_only"
    assert rows[0]["status"] == "approved"
    entry = store.load_entry(rows[0]["tip_sha256"])
    assert entry["model_type"] == "market_baseline"
    assert entry["bundle_path"] is None
    assert entry["feature_set"] == []
    approval = store.load_kind("approval", entry["approval_record_sha256"])
    assert approval["approval_kind"] == "bootstrap_baseline"
    assert "not evidence that the baseline beat itself" in approval["rationale"]
    manifest = json.loads((PACK / "manifest.json").read_text())
    assert "manifest.json" not in manifest["artifacts_sha256"]
    assert manifest.get("excludes_self") is True


def test_nonbaseline_requires_bundle_and_features(repo_tmp: Path) -> None:
    with pytest.raises(ValueError, match="nonempty feature_set"):
        build_registry_entry(
            model_id="x",
            model_version="1",
            model_type="residual_logistic",
            status="candidate",
            protocol_version="1.0.0",
            matrix_schema_version="1.0.0",
            feature_set=[],
            probability_source="x",
            timing_limitations="x",
            evaluation_coverage="x",
            limitations="x",
            serving_requirements="x",
            fallback_behavior="x",
            bundle_path="artifacts/x.json",
            bundle_sha256="a" * 64,
            m10_approved_feature_set_path="docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json",
            m10_approved_feature_set_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="bundle"):
        build_registry_entry(
            model_id="x",
            model_version="1",
            model_type="residual_logistic",
            status="candidate",
            protocol_version="1.0.0",
            matrix_schema_version="1.0.0",
            feature_set=["home_sos"],
            probability_source="x",
            timing_limitations="x",
            evaluation_coverage="x",
            limitations="x",
            serving_requirements="x",
            fallback_behavior="x",
            m10_approved_feature_set_path="docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json",
            m10_approved_feature_set_sha256="b" * 64,
        )


def test_failed_gates_cannot_approve_and_pass_is_eligible_only(repo_tmp: Path) -> None:
    store = RegistryStore(root=repo_tmp / "docs/modeling_artifacts/m12/1.0.0", repo_root=repo_tmp)
    m10_rel, m10_sha = _promoted_m10(repo_tmp, ["feat_a"])
    package = _passing_package(repo_tmp, features=["feat_a"], m10_rel=m10_rel, m10_sha=m10_sha)
    # register candidate
    entry = register_candidate(
        store,
        entry_fields={
            "model_id": "cand_a",
            "model_version": "1.0.0",
            "model_type": "residual_logistic",
            "status": "candidate",
            "protocol_version": "1.0.0",
            "matrix_schema_version": "1.0.0",
            "feature_set": ["feat_a"],
            "probability_source": "residual",
            "timing_limitations": "pre-lock",
            "evaluation_coverage": "test",
            "limitations": "test",
            "serving_requirements": "test",
            "fallback_behavior": "market_only",
            "bundle_path": package.bundle_path,
            "bundle_sha256": package.bundle_sha256,
            "m10_approved_feature_set_path": m10_rel,
            "m10_approved_feature_set_sha256": m10_sha,
        },
    )
    bad = CandidatePackage(**{**package.__dict__, "aggregate_log_loss_candidate": 0.9})
    failed = evaluate_candidate(
        store,
        candidate_entry_sha256=entry["record_sha256"],
        package=bad,
        policy_path="docs/modeling_artifacts/m12/1.0.0/promotion_policy.json",
        evaluated_at_utc="2026-09-04T22:00:00Z",
    )
    assert failed["outcome"] == "failed"
    with pytest.raises(ValueError, match="eligible_for_human_review"):
        approve(
            store,
            model_id="cand_a",
            evaluation_sha256=failed["record_sha256"],
            reviewer="Matt Ryan",
            rationale="nope",
            reviewed_at_utc="2026-09-04T22:01:00Z",
            expected_tip=entry["record_sha256"],
        )

    passed = evaluate_candidate(
        store,
        candidate_entry_sha256=entry["record_sha256"],
        package=package,
        policy_path="docs/modeling_artifacts/m12/1.0.0/promotion_policy.json",
        evaluated_at_utc="2026-09-04T22:02:00Z",
    )
    assert passed["outcome"] == "eligible_for_human_review"
    assert passed["outcome"] != "approved"
    approved = approve(
        store,
        model_id="cand_a",
        evaluation_sha256=passed["record_sha256"],
        reviewer="Matt Ryan",
        rationale="human approval after gates",
        reviewed_at_utc="2026-09-04T22:03:00Z",
        expected_tip=entry["record_sha256"],
    )
    assert approved["status"] == "approved"
    assert approved["prior_record_sha256"] == entry["record_sha256"]
    # prior immutable: colliding filename with different bytes is rejected
    prior_path = store.record_path("entry", entry["record_sha256"])
    original = prior_path.read_text()
    prior_path.write_text("tampered-bytes\n", encoding="utf-8")
    with pytest.raises(ImmutableRecordError):
        store.write_record("entry", entry)
    prior_path.write_text(original, encoding="utf-8")
    assert store.load_entry(entry["record_sha256"])["record_sha256"] == entry[
        "record_sha256"
    ]


def test_review_only_rejected_and_unequal_ids_fail(repo_tmp: Path) -> None:
    store = RegistryStore(root=repo_tmp / "docs/modeling_artifacts/m12/1.0.0", repo_root=repo_tmp)
    m10_rel, m10_sha = _promoted_m10(repo_tmp, ["feat_a"])
    package = _passing_package(
        repo_tmp,
        features=["feat_a"],
        m10_rel=m10_rel,
        m10_sha=m10_sha,
        include_review_only=True,
    )
    entry = register_candidate(
        store,
        entry_fields={
            "model_id": "cand_b",
            "model_version": "1.0.0",
            "model_type": "residual_logistic",
            "protocol_version": "1.0.0",
            "matrix_schema_version": "1.0.0",
            "feature_set": ["feat_a", "home_sos"],
            "probability_source": "residual",
            "timing_limitations": "pre-lock",
            "evaluation_coverage": "test",
            "limitations": "test",
            "serving_requirements": "test",
            "fallback_behavior": "market_only",
            "bundle_path": package.bundle_path,
            "bundle_sha256": package.bundle_sha256,
            "m10_approved_feature_set_path": m10_rel,
            "m10_approved_feature_set_sha256": m10_sha,
        },
    )
    ev = evaluate_candidate(
        store,
        candidate_entry_sha256=entry["record_sha256"],
        package=package,
        policy_path="docs/modeling_artifacts/m12/1.0.0/promotion_policy.json",
        evaluated_at_utc="2026-09-04T22:10:00Z",
    )
    assert ev["outcome"] == "failed"
    assert any(
        g["gate"] == "promoted_features_only" and not g["passed"]
        for g in ev["gate_results"]
    )

    package2 = _passing_package(
        repo_tmp, features=["feat_a"], m10_rel=m10_rel, m10_sha=m10_sha, unequal_ids=True
    )
    # need matching entry features
    entry2 = register_candidate(
        store,
        entry_fields={
            "model_id": "cand_c",
            "model_version": "1.0.0",
            "model_type": "residual_logistic",
            "protocol_version": "1.0.0",
            "matrix_schema_version": "1.0.0",
            "feature_set": ["feat_a"],
            "probability_source": "residual",
            "timing_limitations": "pre-lock",
            "evaluation_coverage": "test",
            "limitations": "test",
            "serving_requirements": "test",
            "fallback_behavior": "market_only",
            "bundle_path": package2.bundle_path,
            "bundle_sha256": package2.bundle_sha256,
            "m10_approved_feature_set_path": m10_rel,
            "m10_approved_feature_set_sha256": m10_sha,
        },
    )
    ev2 = evaluate_candidate(
        store,
        candidate_entry_sha256=entry2["record_sha256"],
        package=package2,
        policy_path="docs/modeling_artifacts/m12/1.0.0/promotion_policy.json",
        evaluated_at_utc="2026-09-04T22:11:00Z",
    )
    assert ev2["outcome"] == "failed"
    assert any(
        g["gate"] == "identical_paired_game_ids" and not g["passed"]
        for g in ev2["gate_results"]
    )


def test_tamper_detected_and_path_safety(repo_tmp: Path) -> None:
    store = RegistryStore(root=repo_tmp / "docs/modeling_artifacts/m12/1.0.0", repo_root=repo_tmp)
    m10 = repo_tmp / "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json"
    m10.write_text(m10.read_text() + "\n")
    with pytest.raises(Exception, match="tampered|hash mismatch"):
        store.validate()

    with pytest.raises(UnsafeRegistryPathError):
        normalize_repo_path(
            "../secret", repo_root=repo_tmp, allowed_roots=("docs/modeling_artifacts/",)
        )
    with pytest.raises(UnsafeRegistryPathError):
        normalize_repo_path(
            "/tmp/x", repo_root=repo_tmp, allowed_roots=("docs/modeling_artifacts/",)
        )


def test_stale_tip_and_retire_terminal(repo_tmp: Path) -> None:
    store = RegistryStore(root=repo_tmp / "docs/modeling_artifacts/m12/1.0.0", repo_root=repo_tmp)
    tip = store.tip("market_only")
    assert tip
    with pytest.raises(StaleTipError):
        store.cas_set_tip("market_only", expected_tip="deadbeef", new_tip=tip)
    retired = retire(
        store,
        model_id="market_only",
        reviewer="Matt Ryan",
        rationale="test retire",
        reviewed_at_utc="2026-09-04T22:20:00Z",
        expected_tip=tip,
    )
    assert retired["status"] == "retired"
    with pytest.raises(ValueError, match="illegal transition"):
        retire(
            store,
            model_id="market_only",
            reviewer="Matt Ryan",
            rationale="again",
            reviewed_at_utc="2026-09-04T22:21:00Z",
            expected_tip=retired["record_sha256"],
        )


def test_bootstrap_exception_broader_approval_fails(repo_tmp: Path) -> None:
    store = RegistryStore(root=repo_tmp / "docs/modeling_artifacts/m12/1.0.0", repo_root=repo_tmp)
    # cannot approve without evaluation for a normal candidate
    m10_rel, m10_sha = _promoted_m10(repo_tmp, ["feat_a"])
    package = _passing_package(repo_tmp, features=["feat_a"], m10_rel=m10_rel, m10_sha=m10_sha)
    entry = register_candidate(
        store,
        entry_fields={
            "model_id": "cand_d",
            "model_version": "1.0.0",
            "model_type": "residual_logistic",
            "protocol_version": "1.0.0",
            "matrix_schema_version": "1.0.0",
            "feature_set": ["feat_a"],
            "probability_source": "residual",
            "timing_limitations": "pre-lock",
            "evaluation_coverage": "test",
            "limitations": "test",
            "serving_requirements": "test",
            "fallback_behavior": "market_only",
            "bundle_path": package.bundle_path,
            "bundle_sha256": package.bundle_sha256,
            "m10_approved_feature_set_path": m10_rel,
            "m10_approved_feature_set_sha256": m10_sha,
        },
    )
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        approve(
            store,
            model_id="cand_d",
            evaluation_sha256="0" * 64,
            reviewer="Matt Ryan",
            rationale="skip gates",
            reviewed_at_utc="2026-09-04T22:30:00Z",
            expected_tip=entry["record_sha256"],
        )


def test_shadow_requires_human_after_eligible(repo_tmp: Path) -> None:
    store = RegistryStore(root=repo_tmp / "docs/modeling_artifacts/m12/1.0.0", repo_root=repo_tmp)
    m10_rel, m10_sha = _promoted_m10(repo_tmp, ["feat_a"])
    package = _passing_package(repo_tmp, features=["feat_a"], m10_rel=m10_rel, m10_sha=m10_sha)
    entry = register_candidate(
        store,
        entry_fields={
            "model_id": "cand_e",
            "model_version": "1.0.0",
            "model_type": "boosted",
            "protocol_version": "1.0.0",
            "matrix_schema_version": "1.0.0",
            "feature_set": ["feat_a"],
            "probability_source": "boosted",
            "timing_limitations": "pre-lock",
            "evaluation_coverage": "test",
            "limitations": "test",
            "serving_requirements": "test",
            "fallback_behavior": "market_only",
            "bundle_path": package.bundle_path,
            "bundle_sha256": package.bundle_sha256,
            "m10_approved_feature_set_path": m10_rel,
            "m10_approved_feature_set_sha256": m10_sha,
        },
    )
    passed = evaluate_candidate(
        store,
        candidate_entry_sha256=entry["record_sha256"],
        package=package,
        policy_path="docs/modeling_artifacts/m12/1.0.0/promotion_policy.json",
        evaluated_at_utc="2026-09-04T22:40:00Z",
    )
    assert passed["outcome"] == "eligible_for_human_review"
    shadow = designate_shadow(
        store,
        model_id="cand_e",
        evaluation_sha256=passed["record_sha256"],
        reviewer="Matt Ryan",
        rationale="shadow only",
        reviewed_at_utc="2026-09-04T22:41:00Z",
        expected_tip=entry["record_sha256"],
    )
    assert shadow["status"] == "shadow"
