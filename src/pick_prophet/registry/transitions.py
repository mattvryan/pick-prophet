"""Human and operator transitions for the M12 registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pick_prophet.registry.records import (
    PERMITTED_TRANSITIONS,
    build_approval_record,
    build_registry_entry,
    build_retirement_record,
)
from pick_prophet.registry.store import RegistryStore, StaleTipError


def register_candidate(
    store: RegistryStore,
    *,
    entry_fields: Mapping[str, Any],
) -> dict[str, Any]:
    """Write a genesis candidate entry and CAS tip from absent → new."""
    fields = dict(entry_fields)
    fields.setdefault("status", "candidate")
    if fields.get("status") != "candidate":
        raise ValueError("register_candidate only creates status=candidate")
    if fields.get("prior_record_sha256") is not None:
        raise ValueError("register_candidate requires genesis prior_record_sha256=None")
    if fields.get("approval_record_sha256") is not None:
        raise ValueError("candidates must not carry approval_record_sha256")
    model_id = str(fields["model_id"])
    if store.tip(model_id) is not None:
        raise StaleTipError(f"model_id already registered: {model_id}")
    entry = build_registry_entry(**fields)
    written = store.write_record("entry", entry)
    store.cas_set_tip(
        model_id,
        expected_tip=None,
        new_tip=written["record_sha256"],
        model_meta={
            "model_type": written["model_type"],
            "model_version": written["model_version"],
        },
    )
    store.rewrite_manifest()
    return written


def _require_eligible_evaluation(
    store: RegistryStore,
    *,
    model_id: str,
    evaluation_sha256: str,
    expected_tip: str,
) -> dict[str, Any]:
    tip = store.tip(model_id)
    if tip != expected_tip:
        raise StaleTipError(
            f"stale tip for {model_id}: expected {expected_tip!r}, found {tip!r}"
        )
    evaluation = store.load_kind("evaluation", evaluation_sha256)
    if evaluation["outcome"] != "eligible_for_human_review":
        raise ValueError(
            "approval/shadow requires evaluation outcome "
            "eligible_for_human_review"
        )
    if evaluation["candidate_entry_sha256"] != expected_tip:
        raise ValueError(
            "evaluation does not target the current lineage tip"
        )
    return evaluation


def approve(
    store: RegistryStore,
    *,
    model_id: str,
    evaluation_sha256: str,
    reviewer: str,
    rationale: str,
    reviewed_at_utc: str,
    expected_tip: str,
) -> dict[str, Any]:
    current = store.load_entry(expected_tip)
    if current["model_id"] != model_id:
        raise ValueError("expected_tip model_id mismatch")
    if (current["status"], "approved") not in PERMITTED_TRANSITIONS:
        raise ValueError(
            f"illegal transition {current['status']!r} -> 'approved'"
        )
    _require_eligible_evaluation(
        store,
        model_id=model_id,
        evaluation_sha256=evaluation_sha256,
        expected_tip=expected_tip,
    )
    approval = build_approval_record(
        model_id=model_id,
        to_status="approved",
        approval_kind="candidate_promotion",
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        rationale=rationale,
        evaluation_record_sha256=evaluation_sha256,
        entry_record_sha256=expected_tip,
    )
    approval = store.write_record("approval", approval)
    new_entry = build_registry_entry(
        model_id=current["model_id"],
        model_version=current["model_version"],
        model_type=current["model_type"],
        status="approved",
        protocol_version=current["protocol_version"],
        matrix_schema_version=current["matrix_schema_version"],
        feature_set=current["feature_set"],
        probability_source=current["probability_source"],
        timing_limitations=current["timing_limitations"],
        evaluation_coverage=current["evaluation_coverage"],
        limitations=current["limitations"],
        serving_requirements=current["serving_requirements"],
        fallback_behavior=current["fallback_behavior"],
        prior_record_sha256=expected_tip,
        m10_approved_feature_set_path=current.get("m10_approved_feature_set_path"),
        m10_approved_feature_set_sha256=current.get(
            "m10_approved_feature_set_sha256"
        ),
        m11_decision_path=current.get("m11_decision_path"),
        m11_decision_sha256=current.get("m11_decision_sha256"),
        bundle_path=current.get("bundle_path"),
        bundle_sha256=current.get("bundle_sha256"),
        metrics_summary=current.get("metrics_summary"),
        approval_record_sha256=approval["record_sha256"],
        evaluation_record_sha256=evaluation_sha256,
    )
    written = store.write_record("entry", new_entry)
    store.cas_set_tip(
        model_id,
        expected_tip=expected_tip,
        new_tip=written["record_sha256"],
        model_meta={"status": "approved"},
    )
    store.rewrite_manifest()
    return written


def designate_shadow(
    store: RegistryStore,
    *,
    model_id: str,
    evaluation_sha256: str,
    reviewer: str,
    rationale: str,
    reviewed_at_utc: str,
    expected_tip: str,
) -> dict[str, Any]:
    current = store.load_entry(expected_tip)
    if current["model_id"] != model_id:
        raise ValueError("expected_tip model_id mismatch")
    if (current["status"], "shadow") not in PERMITTED_TRANSITIONS:
        raise ValueError(
            f"illegal transition {current['status']!r} -> 'shadow'"
        )
    _require_eligible_evaluation(
        store,
        model_id=model_id,
        evaluation_sha256=evaluation_sha256,
        expected_tip=expected_tip,
    )
    approval = build_approval_record(
        model_id=model_id,
        to_status="shadow",
        approval_kind="shadow_designation",
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        rationale=rationale,
        evaluation_record_sha256=evaluation_sha256,
        entry_record_sha256=expected_tip,
    )
    approval = store.write_record("approval", approval)
    new_entry = build_registry_entry(
        model_id=current["model_id"],
        model_version=current["model_version"],
        model_type=current["model_type"],
        status="shadow",
        protocol_version=current["protocol_version"],
        matrix_schema_version=current["matrix_schema_version"],
        feature_set=current["feature_set"],
        probability_source=current["probability_source"],
        timing_limitations=current["timing_limitations"],
        evaluation_coverage=current["evaluation_coverage"],
        limitations=current["limitations"],
        serving_requirements=current["serving_requirements"],
        fallback_behavior=current["fallback_behavior"],
        prior_record_sha256=expected_tip,
        m10_approved_feature_set_path=current.get("m10_approved_feature_set_path"),
        m10_approved_feature_set_sha256=current.get(
            "m10_approved_feature_set_sha256"
        ),
        m11_decision_path=current.get("m11_decision_path"),
        m11_decision_sha256=current.get("m11_decision_sha256"),
        bundle_path=current.get("bundle_path"),
        bundle_sha256=current.get("bundle_sha256"),
        metrics_summary=current.get("metrics_summary"),
        approval_record_sha256=approval["record_sha256"],
        evaluation_record_sha256=evaluation_sha256,
    )
    written = store.write_record("entry", new_entry)
    store.cas_set_tip(
        model_id,
        expected_tip=expected_tip,
        new_tip=written["record_sha256"],
        model_meta={"status": "shadow"},
    )
    store.rewrite_manifest()
    return written


def retire(
    store: RegistryStore,
    *,
    model_id: str,
    reviewer: str,
    rationale: str,
    reviewed_at_utc: str,
    expected_tip: str,
    superseded_by_model_id: str | None = None,
    superseded_by_record_sha256: str | None = None,
) -> dict[str, Any]:
    current = store.load_entry(expected_tip)
    if current["model_id"] != model_id:
        raise ValueError("expected_tip model_id mismatch")
    if (current["status"], "retired") not in PERMITTED_TRANSITIONS:
        raise ValueError(
            f"illegal transition {current['status']!r} -> 'retired'"
        )
    tip = store.tip(model_id)
    if tip != expected_tip:
        raise StaleTipError(
            f"stale tip for {model_id}: expected {expected_tip!r}, found {tip!r}"
        )
    retirement = build_retirement_record(
        model_id=model_id,
        prior_entry_sha256=expected_tip,
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        rationale=rationale,
        superseded_by_model_id=superseded_by_model_id,
        superseded_by_record_sha256=superseded_by_record_sha256,
    )
    retirement = store.write_record("retirement", retirement)
    new_entry = build_registry_entry(
        model_id=current["model_id"],
        model_version=current["model_version"],
        model_type=current["model_type"],
        status="retired",
        protocol_version=current["protocol_version"],
        matrix_schema_version=current["matrix_schema_version"],
        feature_set=current["feature_set"],
        probability_source=current["probability_source"],
        timing_limitations=current["timing_limitations"],
        evaluation_coverage=current["evaluation_coverage"],
        limitations=current["limitations"],
        serving_requirements=current["serving_requirements"],
        fallback_behavior=current["fallback_behavior"],
        prior_record_sha256=expected_tip,
        m10_approved_feature_set_path=current.get("m10_approved_feature_set_path"),
        m10_approved_feature_set_sha256=current.get(
            "m10_approved_feature_set_sha256"
        ),
        m11_decision_path=current.get("m11_decision_path"),
        m11_decision_sha256=current.get("m11_decision_sha256"),
        bundle_path=current.get("bundle_path"),
        bundle_sha256=current.get("bundle_sha256"),
        metrics_summary=current.get("metrics_summary"),
        approval_record_sha256=current.get("approval_record_sha256"),
        retirement_record_sha256=retirement["record_sha256"],
        evaluation_record_sha256=current.get("evaluation_record_sha256"),
    )
    written = store.write_record("entry", new_entry)
    store.cas_set_tip(
        model_id,
        expected_tip=expected_tip,
        new_tip=written["record_sha256"],
        model_meta={"status": "retired"},
    )
    store.rewrite_manifest()
    return written
