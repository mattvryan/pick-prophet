"""Immutable M12 registry record builders and shape validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pick_prophet.registry.hashing import attach_record_sha256

ENTRY_SCHEMA_VERSION = "1.0.0"
APPROVAL_SCHEMA_VERSION = "1.0.0"
EVALUATION_SCHEMA_VERSION = "1.0.0"
RETIREMENT_SCHEMA_VERSION = "1.0.0"
REGISTRY_VERSION = "1.0.0"

LIFECYCLE_STATES = frozenset({"candidate", "shadow", "approved", "retired"})
MODEL_TYPES = frozenset(
    {"market_baseline", "residual_logistic", "boosted", "other"}
)
APPROVAL_KINDS = frozenset(
    {"bootstrap_baseline", "candidate_promotion", "shadow_designation"}
)
EVALUATION_OUTCOMES = frozenset({"failed", "eligible_for_human_review"})

PERMITTED_TRANSITIONS = frozenset(
    {
        (None, "candidate"),
        (None, "approved"),  # bootstrap market_only only; enforced elsewhere
        ("candidate", "shadow"),
        ("candidate", "approved"),
        ("candidate", "retired"),
        ("shadow", "approved"),
        ("shadow", "retired"),
        ("approved", "retired"),
    }
)


def normalize_feature_list(features: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in features:
        name = str(raw).strip()
        if not name:
            raise ValueError("feature names must be non-empty")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"duplicate normalized feature name: {name!r}")
        seen.add(key)
        out.append(name)
    return out


def build_registry_entry(
    *,
    model_id: str,
    model_version: str,
    model_type: str,
    status: str,
    protocol_version: str,
    matrix_schema_version: str,
    feature_set: Sequence[str],
    probability_source: str,
    timing_limitations: str,
    evaluation_coverage: str,
    limitations: str,
    serving_requirements: str,
    fallback_behavior: str,
    prior_record_sha256: str | None = None,
    m10_approved_feature_set_path: str | None = None,
    m10_approved_feature_set_sha256: str | None = None,
    m11_decision_path: str | None = None,
    m11_decision_sha256: str | None = None,
    bundle_path: str | None = None,
    bundle_sha256: str | None = None,
    metrics_summary: Mapping[str, Any] | None = None,
    approval_record_sha256: str | None = None,
    retirement_record_sha256: str | None = None,
    evaluation_record_sha256: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    features = normalize_feature_list(feature_set)
    if status not in LIFECYCLE_STATES:
        raise ValueError(f"unknown lifecycle status: {status!r}")
    if model_type not in MODEL_TYPES:
        raise ValueError(f"unsupported model_type: {model_type!r}")
    if model_type == "market_baseline":
        if features:
            raise ValueError("market_baseline feature_set must be empty")
        if bundle_path is not None or bundle_sha256 is not None:
            raise ValueError("market_baseline must not include a fitted bundle")
    else:
        if not features:
            raise ValueError("non-baseline models require a nonempty feature_set")
        if not bundle_path or not bundle_sha256:
            raise ValueError("non-baseline models require bundle_path and bundle_sha256")
        if not m10_approved_feature_set_path or not m10_approved_feature_set_sha256:
            raise ValueError(
                "non-baseline models require m10 approved feature-set path/hash"
            )
    if status in {"approved", "shadow"} and not approval_record_sha256:
        raise ValueError(f"{status} entries require approval_record_sha256")

    payload: dict[str, Any] = {
        "artifact_schema_version": ENTRY_SCHEMA_VERSION,
        "registry_version": REGISTRY_VERSION,
        "model_id": model_id,
        "model_version": model_version,
        "model_type": model_type,
        "status": status,
        "prior_record_sha256": prior_record_sha256,
        "protocol_version": protocol_version,
        "matrix_schema_version": matrix_schema_version,
        "feature_set": features,
        "m10_approved_feature_set_path": m10_approved_feature_set_path,
        "m10_approved_feature_set_sha256": m10_approved_feature_set_sha256,
        "m11_decision_path": m11_decision_path,
        "m11_decision_sha256": m11_decision_sha256,
        "bundle_path": bundle_path,
        "bundle_sha256": bundle_sha256,
        "probability_source": probability_source,
        "timing_limitations": timing_limitations,
        "evaluation_coverage": evaluation_coverage,
        "limitations": limitations,
        "serving_requirements": serving_requirements,
        "fallback_behavior": fallback_behavior,
        "metrics_summary": dict(metrics_summary) if metrics_summary else None,
        "approval_record_sha256": approval_record_sha256,
        "retirement_record_sha256": retirement_record_sha256,
        "evaluation_record_sha256": evaluation_record_sha256,
    }
    if extra:
        overlap = set(extra) & set(payload)
        if overlap:
            raise ValueError(f"extra fields collide with reserved keys: {sorted(overlap)}")
        payload.update(dict(extra))
    return attach_record_sha256(payload)


def build_approval_record(
    *,
    model_id: str,
    to_status: str,
    approval_kind: str,
    reviewer: str,
    reviewed_at_utc: str,
    rationale: str,
    evaluation_record_sha256: str | None = None,
    entry_record_sha256: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if approval_kind not in APPROVAL_KINDS:
        raise ValueError(f"unknown approval_kind: {approval_kind!r}")
    if to_status not in {"approved", "shadow"}:
        raise ValueError(f"approval to_status must be approved|shadow: {to_status!r}")
    if approval_kind == "bootstrap_baseline":
        if evaluation_record_sha256 is not None:
            raise ValueError("bootstrap_baseline must not reference an evaluation")
        if to_status != "approved":
            raise ValueError("bootstrap_baseline must target approved")
    else:
        if not evaluation_record_sha256:
            raise ValueError(f"{approval_kind} requires evaluation_record_sha256")
    payload = {
        "artifact_schema_version": APPROVAL_SCHEMA_VERSION,
        "model_id": model_id,
        "to_status": to_status,
        "approval_kind": approval_kind,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at_utc,
        "rationale": rationale,
        "evaluation_record_sha256": evaluation_record_sha256,
        "entry_record_sha256": entry_record_sha256,
        "provenance": dict(provenance) if provenance else None,
    }
    return attach_record_sha256(payload)


def build_evaluation_record(
    *,
    candidate_entry_sha256: str,
    baseline_entry_sha256: str,
    promotion_policy_path: str,
    promotion_policy_sha256: str,
    evaluator_version: str,
    evaluated_at_utc: str,
    gate_results: Sequence[Mapping[str, Any]],
    outcome: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if outcome not in EVALUATION_OUTCOMES:
        raise ValueError(f"invalid evaluation outcome: {outcome!r}")
    if outcome == "approved":
        raise ValueError("evaluations must never set approved")
    gates = [dict(item) for item in gate_results]
    if not gates:
        raise ValueError("evaluation requires gate_results")
    for gate in gates:
        if "gate" not in gate or "passed" not in gate or "reason" not in gate:
            raise ValueError("each gate result needs gate, passed, reason")
    if outcome == "eligible_for_human_review" and not all(
        bool(g["passed"]) for g in gates
    ):
        raise ValueError("eligible_for_human_review requires all gates to pass")
    if outcome == "failed" and all(bool(g["passed"]) for g in gates):
        raise ValueError("failed outcome requires at least one failed gate")
    payload = {
        "artifact_schema_version": EVALUATION_SCHEMA_VERSION,
        "candidate_entry_sha256": candidate_entry_sha256,
        "baseline_entry_sha256": baseline_entry_sha256,
        "promotion_policy_path": promotion_policy_path,
        "promotion_policy_sha256": promotion_policy_sha256,
        "evaluator_version": evaluator_version,
        "evaluated_at_utc": evaluated_at_utc,
        "gate_results": gates,
        "outcome": outcome,
        "evidence": dict(evidence),
    }
    return attach_record_sha256(payload)


def build_retirement_record(
    *,
    model_id: str,
    prior_entry_sha256: str,
    reviewer: str,
    reviewed_at_utc: str,
    rationale: str,
    superseded_by_model_id: str | None = None,
    superseded_by_record_sha256: str | None = None,
) -> dict[str, Any]:
    payload = {
        "artifact_schema_version": RETIREMENT_SCHEMA_VERSION,
        "model_id": model_id,
        "prior_entry_sha256": prior_entry_sha256,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at_utc,
        "rationale": rationale,
        "superseded_by_model_id": superseded_by_model_id,
        "superseded_by_record_sha256": superseded_by_record_sha256,
    }
    return attach_record_sha256(payload)


def validate_entry_shape(entry: Mapping[str, Any]) -> None:
    required = {
        "artifact_schema_version",
        "registry_version",
        "record_sha256",
        "model_id",
        "model_version",
        "model_type",
        "status",
        "protocol_version",
        "matrix_schema_version",
        "feature_set",
        "probability_source",
        "timing_limitations",
        "evaluation_coverage",
        "limitations",
        "serving_requirements",
        "fallback_behavior",
    }
    missing = required - set(entry)
    if missing:
        raise ValueError(f"registry entry missing fields: {sorted(missing)}")
    if entry["artifact_schema_version"] != ENTRY_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported entry schema {entry['artifact_schema_version']!r}"
        )
    if entry["status"] not in LIFECYCLE_STATES:
        raise ValueError(f"unknown lifecycle status: {entry['status']!r}")
    if entry["model_type"] not in MODEL_TYPES:
        raise ValueError(f"unsupported model_type: {entry['model_type']!r}")
    features = list(entry["feature_set"] or [])
    normalize_feature_list(features)
    if entry["model_type"] == "market_baseline":
        if features:
            raise ValueError("market_baseline feature_set must be empty")
        if entry.get("bundle_path") or entry.get("bundle_sha256"):
            raise ValueError("market_baseline must not include a fitted bundle")
    else:
        if not features:
            raise ValueError("non-baseline models require a nonempty feature_set")
        if not entry.get("bundle_path") or not entry.get("bundle_sha256"):
            raise ValueError("non-baseline models require a fitted bundle")
    if entry["status"] in {"approved", "shadow"} and not entry.get(
        "approval_record_sha256"
    ):
        raise ValueError(
            f"{entry['status']} entry missing approval_record_sha256"
        )
