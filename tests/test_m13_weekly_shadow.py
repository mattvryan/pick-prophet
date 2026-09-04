"""M13 weekly shadow mode acceptance tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pick_prophet.models.residual_bundle import write_bundle
from pick_prophet.registry.hashing import sha256_file
from pick_prophet.registry.store import RegistryStore
from pick_prophet.weekly.shadow import ShadowRunError, run_weekly_shadow
from pick_prophet.weekly.shadow_select import ShadowSelectionError, select_shadow_model
from pick_prophet.weekly.shadow_serving import (
    BoostedScorer,
    ResidualLogisticScorer,
    ShadowServingError,
    assert_allowlisted_bundle_path,
)

ROOT = Path(__file__).resolve().parents[1]
WEEK1 = ROOT / "weekly" / "2026-W01"
PACK = ROOT / "docs" / "modeling_artifacts" / "m12" / "1.0.0"


def _synthetic_bundle(path: Path, *, feature_names: list[str], beta: list[float]) -> str:
    payload = {
        "bundle_schema_version": "1.0.0",
        "variant": "test",
        "fold_id": "fold0",
        "beta": beta,
        "feature_names": feature_names,
        "lam": 1.0,
        "protocol_version": "1.0.0",
        "matrix_schema_version": "1.0.0",
        "preprocessor": None,
        "source_columns": feature_names,
    }
    return write_bundle(path, payload)


def test_assert_rejects_pickle_paths(tmp_path: Path) -> None:
    bad = tmp_path / "model.pkl"
    bad.write_text("nope", encoding="utf-8")
    with pytest.raises(ShadowServingError, match="unapproved|executable"):
        assert_allowlisted_bundle_path(bad)


def test_residual_scorer_feature_parity_and_hash(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    digest = _synthetic_bundle(bundle_path, feature_names=["x1"], beta=[0.0])
    slate = [
        {
            "cfbd_game_id": "1",
            "home_team": "Home",
            "away_team": "Away",
            "display_order": 1,
        }
    ]
    frame = [
        {
            "cfbd_game_id": "1",
            "home_team": "Home",
            "away_team": "Away",
            "home_market_logit": 0.0,
            "x1": 0.0,
        }
    ]
    entry = {
        "model_id": "cand",
        "model_type": "residual_logistic",
        "record_sha256": "abc",
        "feature_set": ["x1"],
    }
    scored = ResidualLogisticScorer().score(
        slate,
        as_of="2026-08-28T12:00:00Z",
        feature_frame=frame,
        registry_entry=entry,
        bundle_path=bundle_path,
        expected_bundle_sha256=digest,
    )
    assert scored.games[0].p_home == pytest.approx(0.5)
    assert scored.games[0].pick == "Home"

    with pytest.raises(ShadowServingError, match="hash mismatch"):
        ResidualLogisticScorer().score(
            slate,
            as_of="2026-08-28T12:00:00Z",
            feature_frame=frame,
            registry_entry=entry,
            bundle_path=bundle_path,
            expected_bundle_sha256="0" * 64,
        )

    bad_frame = [{**frame[0]}]
    del bad_frame[0]["x1"]
    with pytest.raises(ShadowServingError, match="unavailable"):
        ResidualLogisticScorer().score(
            slate,
            as_of="2026-08-28T12:00:00Z",
            feature_frame=bad_frame,
            registry_entry=entry,
            bundle_path=bundle_path,
            expected_bundle_sha256=digest,
        )

    with pytest.raises(ShadowServingError, match="not implemented"):
        BoostedScorer().score(
            slate,
            as_of="2026-08-28T12:00:00Z",
            feature_frame=frame,
            registry_entry={**entry, "model_type": "boosted"},
            bundle_path=bundle_path,
            expected_bundle_sha256=digest,
        )


def test_selection_no_ml_shadow_on_committed_pack() -> None:
    store = RegistryStore(root=PACK, repo_root=ROOT)
    result = select_shadow_model(store)
    assert result.status == "no_ml_shadow"
    assert result.entry is None


def test_week1_shadow_no_ml_and_immutable(tmp_path: Path) -> None:
    assert WEEK1.joinpath("slate.csv").is_file()
    protected = {
        name: sha256_file(WEEK1 / name)
        for name in ("final_card.md", "submission.json")
        if (WEEK1 / name).is_file()
    }
    out = tmp_path / "shadow-run"
    # as_of before first lock — use a timestamp from early week capture window
    artifacts = run_weekly_shadow(
        slate_path=WEEK1 / "slate.csv",
        as_of="2026-08-28T12:00:00Z",
        output_dir=out,
        registry_root=PACK,
        repo_root=ROOT,
        generation_timestamp="2026-09-04T22:00:00Z",
    )
    manifest = json.loads(artifacts["shadow_manifest"].read_text())
    assert manifest["status"] == "no_ml_shadow"
    assert manifest["label"] == "experimental"
    compare = artifacts["shadow_compare"].read_text()
    assert "market_pick" in compare
    # ML columns present but empty for shadow_pick on no_ml path
    assert "shadow_pick" in compare
    for name, digest in protected.items():
        assert sha256_file(WEEK1 / name) == digest

    # failed run also must not mutate
    with pytest.raises(ShadowRunError, match="non-empty|already exists"):
        run_weekly_shadow(
            slate_path=WEEK1 / "slate.csv",
            as_of="2026-08-28T12:00:00Z",
            output_dir=out,
            registry_root=PACK,
            repo_root=ROOT,
        )
    for name, digest in protected.items():
        assert sha256_file(WEEK1 / name) == digest


def test_incompatible_non_baseline_errors_not_no_ml(tmp_path: Path) -> None:
    pack = tmp_path / "docs" / "modeling_artifacts" / "m12" / "1.0.0"
    shutil.copytree(PACK, pack)
    for rel in (
        "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json",
        "docs/modeling_artifacts/m11/1.0.0/decision.json",
    ):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)

    bundle_path = tmp_path / "artifacts" / "x.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_sha = _synthetic_bundle(bundle_path, feature_names=["x1"], beta=[0.0])

    from pick_prophet.registry.hashing import attach_record_sha256, canonical_dumps

    fake = attach_record_sha256(
        {
            "artifact_schema_version": "1.0.0",
            "registry_version": "1.0.0",
            "model_id": "bogus_ml",
            "model_version": "1.0.0",
            "model_type": "residual_logistic",
            "status": "candidate",
            "prior_record_sha256": None,
            "protocol_version": "1.0.0",
            "matrix_schema_version": "1.0.0",
            "feature_set": ["x1"],
            "m10_approved_feature_set_path": None,
            "m10_approved_feature_set_sha256": None,
            "m11_decision_path": None,
            "m11_decision_sha256": None,
            "bundle_path": "artifacts/x.json",
            "bundle_sha256": bundle_sha,
            "probability_source": "x",
            "timing_limitations": "x",
            "evaluation_coverage": "x",
            "limitations": "x",
            "serving_requirements": "x",
            "fallback_behavior": "x",
            "metrics_summary": None,
            "approval_record_sha256": None,
            "retirement_record_sha256": None,
            "evaluation_record_sha256": None,
        }
    )
    entry_path = pack / "entries" / f"{fake['record_sha256']}.json"
    entry_path.write_text(canonical_dumps(fake) + "\n", encoding="utf-8")
    index = json.loads((pack / "registry_index.json").read_text())
    index["tips"]["bogus_ml"] = fake["record_sha256"]
    index["models"]["bogus_ml"] = {
        "model_type": "residual_logistic",
        "tip_sha256": fake["record_sha256"],
    }
    (pack / "registry_index.json").write_text(
        canonical_dumps(index) + "\n", encoding="utf-8"
    )
    store = RegistryStore(root=pack, repo_root=tmp_path)
    store.rewrite_manifest()
    with pytest.raises(ShadowSelectionError, match="none are eligible"):
        select_shadow_model(store)


def test_protected_output_paths_rejected(tmp_path: Path) -> None:
    with pytest.raises(ShadowRunError, match="week root|protected|recommendations"):
        run_weekly_shadow(
            slate_path=WEEK1 / "slate.csv",
            as_of="2026-08-28T12:00:00Z",
            output_dir=WEEK1,
            registry_root=PACK,
            repo_root=ROOT,
        )
