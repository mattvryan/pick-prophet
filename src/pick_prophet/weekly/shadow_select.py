"""M13 registry tip selection for weekly shadow scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pick_prophet.registry.store import RegistryStore

ML_MODEL_TYPES = frozenset({"residual_logistic", "boosted"})
ELIGIBLE_STATUSES = frozenset({"approved", "shadow"})


@dataclass
class TipRejection:
    model_id: str
    tip_sha256: str
    reasons: list[str]


@dataclass
class SelectionResult:
    status: str  # "ml_shadow" | "no_ml_shadow"
    entry: dict[str, Any] | None = None
    tip_sha256: str | None = None
    reason: str | None = None
    rejections: list[TipRejection] = field(default_factory=list)


class ShadowSelectionError(ValueError):
    """Fail-closed selection failure (not the no_ml_shadow success path)."""


def _is_non_baseline(entry: dict[str, Any]) -> bool:
    return entry.get("model_type") != "market_baseline" and entry.get(
        "model_id"
    ) != "market_only"


def list_current_tips(store: RegistryStore) -> list[tuple[str, str, dict[str, Any]]]:
    store.validate()
    tips = store.load_index().get("tips") or {}
    out: list[tuple[str, str, dict[str, Any]]] = []
    for model_id, tip_sha in sorted(tips.items()):
        entry = store.load_entry(str(tip_sha))
        out.append((str(model_id), str(tip_sha), entry))
    return out


def eligibility_reasons(
    entry: dict[str, Any],
    *,
    tip_sha256: str,
    protocol_version: str,
    matrix_schema_version: str,
) -> list[str]:
    reasons: list[str] = []
    if entry.get("status") not in ELIGIBLE_STATUSES:
        reasons.append(f"status={entry.get('status')!r} not in {sorted(ELIGIBLE_STATUSES)}")
    if entry.get("model_type") not in ML_MODEL_TYPES:
        reasons.append(
            f"model_type={entry.get('model_type')!r} not in {sorted(ML_MODEL_TYPES)}"
        )
    if entry.get("protocol_version") != protocol_version:
        reasons.append(
            f"protocol_version {entry.get('protocol_version')!r} != {protocol_version!r}"
        )
    if entry.get("matrix_schema_version") != matrix_schema_version:
        reasons.append(
            f"matrix_schema_version {entry.get('matrix_schema_version')!r} != "
            f"{matrix_schema_version!r}"
        )
    if not entry.get("feature_set"):
        reasons.append("empty feature_set")
    if not entry.get("bundle_path") or not entry.get("bundle_sha256"):
        reasons.append("missing bundle_path/bundle_sha256")
    if entry.get("record_sha256") != tip_sha256:
        reasons.append("entry record_sha256 does not match tip")
    if entry.get("status") in {"approved", "shadow"} and not entry.get(
        "approval_record_sha256"
    ):
        reasons.append("missing approval_record_sha256")
    return reasons


def select_shadow_model(
    store: RegistryStore,
    *,
    model_id: str | None = None,
    protocol_version: str = "1.0.0",
    matrix_schema_version: str = "1.0.0",
) -> SelectionResult:
    """Deterministic tip selection per M13 design."""
    tips = list_current_tips(store)
    non_baseline = [
        (mid, sha, entry) for mid, sha, entry in tips if _is_non_baseline(entry)
    ]

    if model_id is not None:
        matches = [(mid, sha, entry) for mid, sha, entry in tips if mid == model_id]
        if not matches:
            raise ShadowSelectionError(f"model_id not found in registry tips: {model_id}")
        mid, sha, entry = matches[0]
        if entry.get("status") == "retired":
            raise ShadowSelectionError(f"model_id {model_id} tip is retired")
        if not _is_non_baseline(entry):
            raise ShadowSelectionError(
                f"model_id {model_id} is market_baseline and cannot be an ML shadow"
            )
        reasons = eligibility_reasons(
            entry,
            tip_sha256=sha,
            protocol_version=protocol_version,
            matrix_schema_version=matrix_schema_version,
        )
        if reasons:
            raise ShadowSelectionError(
                f"model_id {model_id} is incompatible: {'; '.join(reasons)}"
            )
        return SelectionResult(
            status="ml_shadow", entry=entry, tip_sha256=sha, reason=None
        )

    if not non_baseline:
        return SelectionResult(
            status="no_ml_shadow",
            reason="no current non-baseline registry tips; sole production tip is market baseline",
        )

    eligible: list[tuple[str, str, dict[str, Any]]] = []
    rejections: list[TipRejection] = []
    for mid, sha, entry in non_baseline:
        reasons = eligibility_reasons(
            entry,
            tip_sha256=sha,
            protocol_version=protocol_version,
            matrix_schema_version=matrix_schema_version,
        )
        if reasons:
            rejections.append(TipRejection(mid, sha, reasons))
        else:
            eligible.append((mid, sha, entry))

    if not eligible:
        detail = "; ".join(
            f"{r.model_id}:{','.join(r.reasons)}" for r in rejections
        )
        raise ShadowSelectionError(
            "non-baseline tip(s) exist but none are eligible for ML shadow: "
            + detail
        )
    if len(eligible) > 1:
        ids = ", ".join(mid for mid, _, _ in eligible)
        raise ShadowSelectionError(
            f"multiple eligible ML tips require --model-id: {ids}"
        )
    mid, sha, entry = eligible[0]
    return SelectionResult(
        status="ml_shadow",
        entry=entry,
        tip_sha256=sha,
        reason=None,
        rejections=rejections,
    )
