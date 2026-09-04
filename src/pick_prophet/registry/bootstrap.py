"""Bootstrap the committed M12 v1 registry pack (market_only only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pick_prophet.registry.hashing import canonical_dumps, sha256_file
from pick_prophet.registry.policy import default_promotion_policy
from pick_prophet.registry.records import build_approval_record, build_registry_entry
from pick_prophet.registry.store import RegistryStore

DEFAULT_PACK_REL = "docs/modeling_artifacts/m12/1.0.0"
M10_REL = "docs/modeling_artifacts/m10/1.0.0/approved_feature_set.json"
M11_REL = "docs/modeling_artifacts/m11/1.0.0/decision.json"


def bootstrap_m12_v1(
    *,
    repo_root: Path,
    reviewer: str,
    reviewed_at_utc: str,
    pack_rel: str = DEFAULT_PACK_REL,
) -> Path:
    """Create the v1 pack with approved market_only and promotion policy."""
    root = repo_root / pack_rel
    if root.exists() and any(root.rglob("*")):
        raise FileExistsError(
            f"refusing to bootstrap over non-empty registry pack: {root}"
        )

    root.mkdir(parents=True, exist_ok=True)
    for name in ("entries", "evaluations", "approvals", "retirements"):
        (root / name).mkdir(exist_ok=True)

    m10_path = repo_root / M10_REL
    m11_path = repo_root / M11_REL
    m10_sha = sha256_file(m10_path)
    m11_sha = sha256_file(m11_path)
    m11 = json.loads(m11_path.read_text())
    if m11.get("status") != "not_run_no_promoted_features":
        raise ValueError(
            "M11 decision status must be not_run_no_promoted_features for v1 bootstrap"
        )

    policy = default_promotion_policy()
    policy_path = root / "promotion_policy.json"
    policy_path.write_text(canonical_dumps(policy) + "\n", encoding="utf-8")

    store = RegistryStore(root=root, repo_root=repo_root)

    approval = build_approval_record(
        model_id="market_only",
        to_status="approved",
        approval_kind="bootstrap_baseline",
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        rationale=(
            "Bootstrap governance decision: retain market_only as the sole "
            "approved production baseline. This is not evidence that the "
            "baseline beat itself. M10 promoted no features; M11 recorded "
            "not_run_no_promoted_features; retaining market_only with no "
            "challenger is a valid successful outcome."
        ),
        provenance={
            "m10_approved_feature_set_path": M10_REL,
            "m10_approved_feature_set_sha256": m10_sha,
            "m11_decision_path": M11_REL,
            "m11_decision_sha256": m11_sha,
            "m11_status": m11.get("status"),
            "bootstrap": True,
        },
    )
    approval = store.write_record("approval", approval)

    entry = build_registry_entry(
        model_id="market_only",
        model_version="1.0.0",
        model_type="market_baseline",
        status="approved",
        protocol_version="1.0.0",
        matrix_schema_version="1.0.0",
        feature_set=[],
        probability_source=(
            "Vig-removed two-way moneyline implied probability / market logit "
            "from pre-lock CFBD market snapshots when available."
        ),
        timing_limitations=(
            "Probabilities require pre-lock market availability; missing "
            "moneylines yield no market probability for that game."
        ),
        evaluation_coverage=(
            "Market baseline is market-derived (not a fitted challenger). "
            "M10 feature evidence covered held-out seasons 2022–2025 only."
        ),
        limitations=(
            "No ML residual/boosted challenger is registered. Approval is "
            "bootstrap governance, not a self-comparison win."
        ),
        serving_requirements=(
            "Serve market probabilities with documented provenance; do not "
            "require a fitted model bundle."
        ),
        fallback_behavior=(
            "market_only is the production fallback and the approved baseline."
        ),
        prior_record_sha256=None,
        m10_approved_feature_set_path=M10_REL,
        m10_approved_feature_set_sha256=m10_sha,
        m11_decision_path=M11_REL,
        m11_decision_sha256=m11_sha,
        bundle_path=None,
        bundle_sha256=None,
        approval_record_sha256=approval["record_sha256"],
        extra={
            "no_challenger_provenance": {
                "m11_status": m11.get("status"),
                "challenger_trained": m11.get("challenger_trained"),
                "baseline_retained": m11.get("baseline_retained"),
            }
        },
    )
    entry = store.write_record("entry", entry)
    store.cas_set_tip(
        "market_only",
        expected_tip=None,
        new_tip=entry["record_sha256"],
        model_meta={
            "model_type": "market_baseline",
            "model_version": "1.0.0",
            "status": "approved",
        },
    )
    store.rewrite_manifest()
    store.validate()
    return root


def bootstrap_summary(repo_root: Path, pack_rel: str = DEFAULT_PACK_REL) -> dict[str, Any]:
    store = RegistryStore(root=repo_root / pack_rel, repo_root=repo_root)
    store.validate()
    return {
        "pack": pack_rel,
        "models": store.list_models(),
    }
