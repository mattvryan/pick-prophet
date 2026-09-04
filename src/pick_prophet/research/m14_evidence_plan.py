"""Generate the frozen M14 evidence-gap and planning artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

M14_ARTIFACT_VERSION = "2.0.0"
Z_975 = 1.959963984540054
Z_80 = 0.8416212335729143


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def build_power_rows(bootstrap_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Estimate planning MDEs from M10 week-cluster bootstrap interval widths.

    This is deliberately a diagnostic approximation, not a prospective power
    guarantee. It preserves the observed cluster dependence in the input CI and
    uses square-root sample scaling only to illustrate order of magnitude.
    """

    keep = {
        "single__home_sos",
        "family__site_temporal",
        "family__history",
        "family__market_context",
        "combined",
    }
    result: list[dict[str, Any]] = []
    for row in bootstrap_rows:
        if (
            row["variant"] not in keep
            or row["slice"] != "overall"
            or row["metric"] not in {"log_loss", "brier"}
        ):
            continue
        low = float(row["ci_low"])
        high = float(row["ci_high"])
        se = (high - low) / (2 * Z_975)
        mde = (Z_975 + Z_80) * se
        n = int(row["n_rows"])
        result.append(
            {
                "variant": row["variant"],
                "metric": row["metric"],
                "observed_delta_candidate_minus_market": float(row["delta"]),
                "ci_low": low,
                "ci_high": high,
                "n_games": n,
                "n_week_clusters": int(row["n_clusters"]),
                "approx_current_mde_80pct_two_sided": mde,
                "approx_mde_at_6000_games": mde * math.sqrt(n / 6000),
                "interpretation": "planning_approximation_not_promotion_evidence",
            }
        )
    return sorted(result, key=lambda item: (item["variant"], item["metric"]))


def generate_m14_artifacts(repo_root: Path, output_dir: Path) -> dict[str, Path]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    m10 = repo_root / "docs/modeling_artifacts/m10/1.0.0"
    sources = {
        "m10_manifest": m10 / "manifest.json",
        "m10_bootstrap": m10 / "paired_bootstrap.csv",
        "m10_approved_features": m10 / "approved_feature_set.json",
        "pickem_inventory": repo_root / "docs/pickem_inventory.md",
        "ratings_feasibility": repo_root / "docs/ratings_feasibility.md",
        "research_protocol_2": repo_root / "docs/research_protocol_2.md",
        "experiment_ledger_2": repo_root / "docs/experiment_ledger_2.json",
    }
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing M14 inputs: {missing}")

    manifest = _load_json(sources["m10_manifest"])
    approved = _load_json(sources["m10_approved_features"])
    if manifest.get("inference_seasons") != [2022, 2023, 2024, 2025]:
        raise ValueError("M14 is frozen to the audited M10 2022-2025 window")
    if approved.get("status") != "no_features_promoted":
        raise ValueError("unexpected M10 disposition; redesign M14 before continuing")

    power_path = output_dir / "power_analysis.csv"
    _write_csv(power_path, build_power_rows(_read_csv(sources["m10_bootstrap"])))

    gaps_path = output_dir / "evidence_gaps.csv"
    _write_csv(
        gaps_path,
        [
            {
                "gap_id": "espn_sampling_frame",
                "current_evidence": "no_verified_historical_archives",
                "impact": "target_population_generalization_unknown",
                "next_milestone": "M15",
                "priority": 1,
            },
            {
                "gap_id": "market_observation_timing",
                "current_evidence": "closing_like_without_observation_timestamp",
                "impact": "baseline_timing_mismatch_and_no_valid_movement",
                "next_milestone": "M16",
                "priority": 2,
            },
            {
                "gap_id": "weekly_team_strength",
                "current_evidence": "elo_publication_time_unproven_fpi_sp_unavailable",
                "impact": "independent_rating_disagreement_untested",
                "next_milestone": "M17",
                "priority": 3,
            },
            {
                "gap_id": "team_efficiency",
                "current_evidence": "coarse_record_and_sos_only",
                "impact": "on_field_form_poorly_measured",
                "next_milestone": "M18",
                "priority": 4,
            },
            {
                "gap_id": "early_season_personnel",
                "current_evidence": "no_dated_qb_roster_or_staff_history",
                "impact": "weeks_1_3_prior_is_weak",
                "next_milestone": "M19",
                "priority": 5,
            },
        ],
    )

    summary = {
        "artifact_version": M14_ARTIFACT_VERSION,
        "protocol_version": "2.0.0",
        "status": "protocol_frozen_sources_not_yet_evaluated",
        "historical_research_seasons": list(range(2017, 2026)),
        "proper_score_inference_seasons_available": [2022, 2023, 2024, 2025],
        "proper_score_games": 3195,
        "week_clusters": 66,
        "verified_historical_espn_slates": 0,
        "m10_outcome": "no_features_promoted",
        "observed_diagnosis": [
            "all tested family-level log-loss confidence intervals crossed zero",
            "market-context aggregate direction was favorable but season-unstable",
            "historical Pick'em target-frame evidence is absent",
            "opening and movement fields were unavailable for evidence",
            "2020 anomalous-season sensitivity was unavailable",
        ],
        "power_analysis_limitation": (
            "MDE values approximate scale from M10 week-cluster bootstrap CI widths; "
            "they are planning diagnostics, not promotion evidence or guarantees."
        ),
        "prospective_holdout": "2026_weekly_shadow_locked",
        "prospective_use": "operations_and_one_time_future_assessment_only",
    }
    summary_path = output_dir / "evidence_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    output_files = [power_path, gaps_path, summary_path]
    artifact_manifest = {
        "artifact_set": "m14_evidence_plan",
        "artifact_version": M14_ARTIFACT_VERSION,
        "protocol_version": "2.0.0",
        "source_sha256": {
            str(path.relative_to(repo_root)): _sha256(path) for path in sources.values()
        },
        "artifacts_sha256": {path.name: _sha256(path) for path in output_files},
        "generated_by": "pick_prophet.research.m14_evidence_plan",
        "contains_2026_outcomes": False,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(artifact_manifest, indent=2, sort_keys=True) + "\n"
    )
    return {
        "summary": summary_path,
        "power": power_path,
        "gaps": gaps_path,
        "manifest": manifest_path,
    }
