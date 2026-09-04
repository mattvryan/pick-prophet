"""Promotion evaluator: automated gates only (never approves)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pick_prophet.models.approved_feature_set import load_approved_feature_set
from pick_prophet.registry.hashing import sha256_file
from pick_prophet.registry.paths import normalize_repo_path, resolve_safe
from pick_prophet.registry.policy import load_promotion_policy
from pick_prophet.registry.records import (
    build_evaluation_record,
    normalize_feature_list,
)
from pick_prophet.registry.store import RegistryStore

EVALUATOR_VERSION = "1.0.0"


@dataclass
class CandidatePackage:
    """Evidence package for evaluating a non-baseline candidate."""

    protocol_version: str
    matrix_schema_version: str
    feature_set: Sequence[str]
    m10_approved_feature_set_path: str
    m10_approved_feature_set_sha256: str
    bundle_path: str
    bundle_sha256: str
    candidate_predictions_path: str
    candidate_predictions_sha256: str
    baseline_predictions_path: str
    baseline_predictions_sha256: str
    paired_game_ids_candidate: Sequence[int]
    paired_game_ids_baseline: Sequence[int]
    seasons: Sequence[int]
    games_per_season: Mapping[int, int]
    aggregate_log_loss_candidate: float
    aggregate_log_loss_baseline: float
    aggregate_brier_candidate: float
    aggregate_brier_baseline: float
    log_loss_ci_low: float
    log_loss_ci_high: float
    brier_ci_low: float
    brier_ci_high: float
    per_season_delta_log_loss: Mapping[int, float]
    per_season_delta_brier: Mapping[int, float]
    calibration_candidate: float
    calibration_baseline: float
    prediction_coverage: float
    timing_classification: str
    leakage_status: str
    leakage_evidence_path: str | None = None
    leakage_evidence_sha256: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: Path) -> CandidatePackage:
        raw = json.loads(Path(path).read_text())
        if not isinstance(raw, dict):
            raise TypeError("candidate package must be a JSON object")
        games_per_season = {
            int(k): int(v) for k, v in dict(raw["games_per_season"]).items()
        }
        per_ll = {
            int(k): float(v)
            for k, v in dict(raw["per_season_delta_log_loss"]).items()
        }
        per_br = {
            int(k): float(v)
            for k, v in dict(raw["per_season_delta_brier"]).items()
        }
        return cls(
            protocol_version=str(raw["protocol_version"]),
            matrix_schema_version=str(raw["matrix_schema_version"]),
            feature_set=list(raw["feature_set"]),
            m10_approved_feature_set_path=str(raw["m10_approved_feature_set_path"]),
            m10_approved_feature_set_sha256=str(
                raw["m10_approved_feature_set_sha256"]
            ),
            bundle_path=str(raw["bundle_path"]),
            bundle_sha256=str(raw["bundle_sha256"]),
            candidate_predictions_path=str(raw["candidate_predictions_path"]),
            candidate_predictions_sha256=str(raw["candidate_predictions_sha256"]),
            baseline_predictions_path=str(raw["baseline_predictions_path"]),
            baseline_predictions_sha256=str(raw["baseline_predictions_sha256"]),
            paired_game_ids_candidate=[int(x) for x in raw["paired_game_ids_candidate"]],
            paired_game_ids_baseline=[int(x) for x in raw["paired_game_ids_baseline"]],
            seasons=[int(x) for x in raw["seasons"]],
            games_per_season=games_per_season,
            aggregate_log_loss_candidate=float(raw["aggregate_log_loss_candidate"]),
            aggregate_log_loss_baseline=float(raw["aggregate_log_loss_baseline"]),
            aggregate_brier_candidate=float(raw["aggregate_brier_candidate"]),
            aggregate_brier_baseline=float(raw["aggregate_brier_baseline"]),
            log_loss_ci_low=float(raw["log_loss_ci_low"]),
            log_loss_ci_high=float(raw["log_loss_ci_high"]),
            brier_ci_low=float(raw["brier_ci_low"]),
            brier_ci_high=float(raw["brier_ci_high"]),
            per_season_delta_log_loss=per_ll,
            per_season_delta_brier=per_br,
            calibration_candidate=float(raw["calibration_candidate"]),
            calibration_baseline=float(raw["calibration_baseline"]),
            prediction_coverage=float(raw["prediction_coverage"]),
            timing_classification=str(raw["timing_classification"]),
            leakage_status=str(raw["leakage_status"]),
            leakage_evidence_path=raw.get("leakage_evidence_path"),
            leakage_evidence_sha256=raw.get("leakage_evidence_sha256"),
            extra=dict(raw.get("extra") or {}),
        )


def _gate(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"gate": name, "passed": bool(passed), "reason": reason}


def _paired_id_digest(ids: Sequence[int]) -> str:
    payload = ",".join(str(i) for i in sorted(int(x) for x in ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_candidate(
    store: RegistryStore,
    *,
    candidate_entry_sha256: str,
    baseline_entry_sha256: str | None = None,
    package: CandidatePackage,
    policy_path: str,
    evaluated_at_utc: str,
) -> dict[str, Any]:
    """Run automated gates and write an evaluation record (never approved)."""
    candidate = store.load_entry(candidate_entry_sha256)
    if candidate["status"] == "retired":
        raise ValueError("cannot evaluate a retired lineage tip")
    tip = store.tip(candidate["model_id"])
    if tip != candidate_entry_sha256:
        raise ValueError(
            f"evaluation targets stale tip for {candidate['model_id']}: "
            f"expected {tip}, got {candidate_entry_sha256}"
        )
    if candidate["model_type"] == "market_baseline":
        raise ValueError("market_baseline is not evaluated as a challenger")

    if baseline_entry_sha256 is None:
        baseline_tip = store.tip("market_only")
        if not baseline_tip:
            raise ValueError("market_only baseline tip missing from registry")
        baseline_entry_sha256 = baseline_tip
    baseline = store.load_entry(baseline_entry_sha256)
    if baseline["model_id"] != "market_only" or baseline["status"] != "approved":
        raise ValueError("comparison baseline must be approved market_only")

    policy_norm = normalize_repo_path(
        policy_path, repo_root=store.repo_root, allowed_roots=store.allowed_roots
    )
    policy_file = resolve_safe(
        policy_norm, repo_root=store.repo_root, allowed_roots=store.allowed_roots
    )
    policy = load_promotion_policy(policy_file)

    gates: list[dict[str, Any]] = []

    # 1. protocol / schema compatibility
    proto_ok = (
        package.protocol_version == candidate["protocol_version"]
        and package.protocol_version == baseline["protocol_version"]
    )
    schema_ok = (
        package.matrix_schema_version == candidate["matrix_schema_version"]
        and package.matrix_schema_version == baseline["matrix_schema_version"]
    )
    gates.append(
        _gate(
            "protocol_schema_compatibility",
            proto_ok and schema_ok,
            "protocol/matrix schema match"
            if proto_ok and schema_ok
            else "protocol or matrix schema mismatch",
        )
    )

    # 2. artifact hashes
    hash_ok = True
    hash_reasons: list[str] = []
    for path, expected in (
        (package.bundle_path, package.bundle_sha256),
        (package.candidate_predictions_path, package.candidate_predictions_sha256),
        (package.baseline_predictions_path, package.baseline_predictions_sha256),
        (package.m10_approved_feature_set_path, package.m10_approved_feature_set_sha256),
    ):
        try:
            norm = normalize_repo_path(
                path, repo_root=store.repo_root, allowed_roots=store.allowed_roots
            )
            resolved = resolve_safe(
                norm, repo_root=store.repo_root, allowed_roots=store.allowed_roots
            )
            if not resolved.is_file():
                hash_ok = False
                hash_reasons.append(f"missing {path}")
                continue
            actual = sha256_file(resolved)
            if actual != expected:
                hash_ok = False
                hash_reasons.append(f"hash mismatch {path}")
        except Exception as exc:  # noqa: BLE001 - gate failure reason
            hash_ok = False
            hash_reasons.append(f"{path}: {exc}")
    if candidate.get("bundle_sha256") != package.bundle_sha256:
        hash_ok = False
        hash_reasons.append("candidate entry bundle hash != package")
    gates.append(
        _gate(
            "immutable_artifact_hashes",
            hash_ok,
            "all artifact hashes match" if hash_ok else "; ".join(hash_reasons),
        )
    )

    # 3. paired IDs
    cand_ids = [int(x) for x in package.paired_game_ids_candidate]
    base_ids = [int(x) for x in package.paired_game_ids_baseline]
    paired_ok = sorted(cand_ids) == sorted(base_ids) and len(cand_ids) == len(
        set(cand_ids)
    )
    paired_digest = _paired_id_digest(cand_ids) if paired_ok else None
    gates.append(
        _gate(
            "identical_paired_game_ids",
            paired_ok,
            "paired held-out game IDs identical"
            if paired_ok
            else "paired held-out game ID sets differ",
        )
    )

    delta_ll = (
        package.aggregate_log_loss_candidate - package.aggregate_log_loss_baseline
    )
    delta_br = package.aggregate_brier_candidate - package.aggregate_brier_baseline

    # 4–5. proper score improvements
    ll_ok = delta_ll <= float(policy["log_loss_improvement_max_delta"])
    gates.append(
        _gate(
            "held_out_log_loss_improvement",
            ll_ok,
            f"delta_log_loss={delta_ll} max_delta={policy['log_loss_improvement_max_delta']}",
        )
    )
    br_ok = delta_br <= float(policy["brier_improvement_max_delta"])
    gates.append(
        _gate(
            "held_out_brier_improvement",
            br_ok,
            f"delta_brier={delta_br} max_delta={policy['brier_improvement_max_delta']}",
        )
    )

    # uncertainty
    if policy["require_uncertainty_ci_excludes_zero"]:
        unc_ok = package.log_loss_ci_high < 0 and package.brier_ci_high < 0
        unc_reason = (
            "log-loss and Brier CIs entirely below zero"
            if unc_ok
            else "uncertainty CI does not exclude zero improvement"
        )
    else:
        unc_ok = True
        unc_reason = "uncertainty CI exclusion not required by policy"
    gates.append(_gate("uncertainty_criterion", unc_ok, unc_reason))

    # 6. calibration regression
    calib_reg = package.calibration_candidate - package.calibration_baseline
    calib_ok = calib_reg <= float(policy["max_calibration_regression"])
    gates.append(
        _gate(
            "no_material_calibration_regression",
            calib_ok,
            f"calibration_regression={calib_reg} "
            f"max={policy['max_calibration_regression']}",
        )
    )

    # 7. season consistency + sample sizes
    seasons = [int(s) for s in package.seasons]
    n_games = len(cand_ids)
    min_n = int(policy["min_paired_games"])
    min_seasons = int(policy["min_test_seasons"])
    min_per = int(policy["min_games_per_season"])
    per = {int(k): int(v) for k, v in package.games_per_season.items()}
    sample_ok = (
        n_games >= min_n
        and len(seasons) >= min_seasons
        and all(per.get(s, 0) >= min_per for s in seasons)
    )
    gates.append(
        _gate(
            "sample_size_requirements",
            sample_ok,
            f"n={n_games} seasons={len(seasons)} per_season={per}",
        )
    )
    ll_improve_seasons = sum(
        1
        for s in seasons
        if float(package.per_season_delta_log_loss.get(s, 1.0))
        <= float(policy["log_loss_improvement_max_delta"])
    )
    br_improve_seasons = sum(
        1
        for s in seasons
        if float(package.per_season_delta_brier.get(s, 1.0))
        <= float(policy["brier_improvement_max_delta"])
    )
    season_ok = ll_improve_seasons >= int(
        policy["min_seasons_improving_log_loss"]
    ) and br_improve_seasons >= int(policy["min_seasons_improving_brier"])
    gates.append(
        _gate(
            "multi_season_improvement",
            season_ok,
            f"ll_seasons={ll_improve_seasons} br_seasons={br_improve_seasons}",
        )
    )

    # 8. coverage + timing
    cov_ok = float(package.prediction_coverage) >= float(
        policy["min_prediction_coverage"]
    )
    timing_ok = package.timing_classification in set(
        policy["allowed_timing_classifications"]
    )
    gates.append(
        _gate(
            "coverage_and_prelock",
            cov_ok and timing_ok,
            f"coverage={package.prediction_coverage} "
            f"timing={package.timing_classification}",
        )
    )

    # 9. leakage
    leak_fail = set(policy["fail_closed_leakage_statuses"])
    leak_ok = package.leakage_status not in leak_fail
    gates.append(
        _gate(
            "no_unresolved_leakage",
            leak_ok,
            f"leakage_status={package.leakage_status}",
        )
    )

    # 10–11. features + bundle / nonempty
    features = normalize_feature_list(package.feature_set)
    feature_ok = True
    feature_reason = "features ⊆ promoted_features"
    try:
        m10_path = resolve_safe(
            normalize_repo_path(
                package.m10_approved_feature_set_path,
                repo_root=store.repo_root,
                allowed_roots=store.allowed_roots,
            ),
            repo_root=store.repo_root,
            allowed_roots=store.allowed_roots,
        )
        approved = load_approved_feature_set(m10_path)
        if sha256_file(m10_path) != package.m10_approved_feature_set_sha256:
            feature_ok = False
            feature_reason = "M10 approved feature-set hash mismatch"
        else:
            promoted = {str(x) for x in approved.get("promoted_features") or []}
            review_only = {str(x) for x in approved.get("review_only_features") or []}
            rejected = {str(x) for x in approved.get("rejected_features") or []}
            unavailable = {str(x) for x in approved.get("unavailable_features") or []}
            bad_review = sorted(set(features) & review_only)
            bad_rej = sorted(set(features) & rejected)
            bad_unavail = sorted(set(features) & unavailable)
            unknown = sorted(set(features) - promoted - review_only - rejected - unavailable)
            # unknown relative to M10 lists that aren't promoted still fail
            not_promoted = sorted(set(features) - promoted)
            if not features:
                feature_ok = False
                feature_reason = "empty feature set for non-baseline model"
            elif bad_review or bad_rej or bad_unavail or not_promoted:
                feature_ok = False
                feature_reason = (
                    f"ineligible features review_only={bad_review} "
                    f"rejected={bad_rej} unavailable={bad_unavail} "
                    f"not_promoted={not_promoted} unknown={unknown}"
                )
            elif set(features) != set(candidate.get("feature_set") or []):
                feature_ok = False
                feature_reason = "package features != candidate entry feature_set"
    except Exception as exc:  # noqa: BLE001
        feature_ok = False
        feature_reason = str(exc)
    gates.append(_gate("promoted_features_only", feature_ok, feature_reason))

    bundle_ok = bool(package.bundle_path and package.bundle_sha256 and features)
    gates.append(
        _gate(
            "nonbaseline_bundle_and_features",
            bundle_ok,
            "bundle and nonempty features present"
            if bundle_ok
            else "missing bundle or empty features",
        )
    )

    outcome = (
        "eligible_for_human_review"
        if all(bool(g["passed"]) for g in gates)
        else "failed"
    )
    evidence = {
        "paired_game_id_digest": paired_digest,
        "paired_game_count": n_games,
        "seasons": seasons,
        "games_per_season": {str(k): v for k, v in per.items()},
        "aggregate_log_loss_candidate": package.aggregate_log_loss_candidate,
        "aggregate_log_loss_baseline": package.aggregate_log_loss_baseline,
        "aggregate_brier_candidate": package.aggregate_brier_candidate,
        "aggregate_brier_baseline": package.aggregate_brier_baseline,
        "delta_log_loss": delta_ll,
        "delta_brier": delta_br,
        "log_loss_ci": [package.log_loss_ci_low, package.log_loss_ci_high],
        "brier_ci": [package.brier_ci_low, package.brier_ci_high],
        "per_season_delta_log_loss": {
            str(k): float(v) for k, v in package.per_season_delta_log_loss.items()
        },
        "per_season_delta_brier": {
            str(k): float(v) for k, v in package.per_season_delta_brier.items()
        },
        "calibration_candidate": package.calibration_candidate,
        "calibration_baseline": package.calibration_baseline,
        "calibration_regression": calib_reg,
        "prediction_coverage": package.prediction_coverage,
        "timing_classification": package.timing_classification,
        "leakage_status": package.leakage_status,
        "feature_set": features,
        "m10_approved_feature_set_path": package.m10_approved_feature_set_path,
        "m10_approved_feature_set_sha256": package.m10_approved_feature_set_sha256,
        "candidate_predictions_path": package.candidate_predictions_path,
        "candidate_predictions_sha256": package.candidate_predictions_sha256,
        "baseline_predictions_path": package.baseline_predictions_path,
        "baseline_predictions_sha256": package.baseline_predictions_sha256,
        "bundle_path": package.bundle_path,
        "bundle_sha256": package.bundle_sha256,
    }
    record = build_evaluation_record(
        candidate_entry_sha256=candidate_entry_sha256,
        baseline_entry_sha256=baseline_entry_sha256,
        promotion_policy_path=policy_norm,
        promotion_policy_sha256=str(policy["_sha256"]),
        evaluator_version=EVALUATOR_VERSION,
        evaluated_at_utc=evaluated_at_utc,
        gate_results=gates,
        outcome=outcome,
        evidence=evidence,
    )
    return store.write_record("evaluation", record)
