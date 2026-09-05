"""Protocol 2.0 incremental-value study for M18/M19 candidate families."""

from __future__ import annotations

import csv
import json
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
from typing import Any

from pick_prophet.evaluation.cluster_bootstrap import (
    bootstrap_paired_delta_clusters,
)
from pick_prophet.evaluation.holm import holm_adjust
from pick_prophet.evaluation.metrics import calibration_bins, score_probabilities
from pick_prophet.features.matrix_v2 import (
    CANDIDATE_FAMILIES,
    M20_CANDIDATE_COLUMNS,
    MATRIX_SCHEMA_VERSION,
)
from pick_prophet.models.residual_fit import fit_residual_walkforward

INFERENCE_SEASONS = (2022, 2023, 2024, 2025)


def build_variants() -> dict[str, tuple[str, ...]]:
    variants: dict[str, tuple[str, ...]] = {"market_only": ()}
    for family, columns in CANDIDATE_FAMILIES.items():
        for column in columns:
            variants[f"single__{family}__{column}"] = (column,)
        variants[f"family__{family}"] = columns
    variants["combined"] = M20_CANDIDATE_COLUMNS
    for family, columns in CANDIDATE_FAMILIES.items():
        removed = set(columns)
        variants[f"lof__without_{family}"] = tuple(
            column for column in M20_CANDIDATE_COLUMNS if column not in removed
        )
    return variants


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _ece(y: list[int], p: list[float]) -> float:
    bins = calibration_bins(y, p, n_bins=10)
    return sum(
        row["count"] * abs(row["mean_predicted"] - row["mean_outcome"])
        for row in bins
        if row["count"]
    ) / len(y)


def _paired(
    predictions: list[dict[str, str]], matrix: dict[int, dict[str, str]], variant: str
) -> list[dict[str, Any]]:
    models: dict[tuple[str, int], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in predictions:
        if int(row["test_season"]) not in INFERENCE_SEASONS:
            continue
        models[(row["fold_id"], int(row["game_id"]))][row["model"]] = row
    output = []
    for (_, game_id), values in sorted(models.items()):
        if "market_only" not in values or variant not in values:
            raise ValueError(f"unpaired predictions for {variant}, game {game_id}")
        market = values["market_only"]
        candidate = values[variant]
        source = matrix[game_id]
        output.append(
            {
                "game_id": game_id,
                "season": int(candidate["test_season"]),
                "season_type": source.get("season_type") or "regular",
                "week": int(float(candidate["week"])),
                "y": int(float(candidate["y_true"])),
                "market": float(market["p_home"]),
                "candidate": float(candidate["p_home"]),
            }
        )
    return output


def _evaluate_variant(
    variant: str, paired: list[dict[str, Any]], *, n_boot: int, seed: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    y = [row["y"] for row in paired]
    market = [row["market"] for row in paired]
    candidate = [row["candidate"] for row in paired]
    clusters = [
        (row["season"], row["season_type"], row["week"]) for row in paired
    ]
    market_score = score_probabilities(y, market)
    candidate_score = score_probabilities(y, candidate)
    boots = {}
    for metric in ("log_loss", "brier"):
        boots[metric] = bootstrap_paired_delta_clusters(
            clusters,
            y,
            market,
            candidate,
            metric=metric,
            n_boot=n_boot,
            seed=seed,
            contrast_id=f"m20:{variant}:{metric}",
        )
    season_rows = []
    for season in INFERENCE_SEASONS:
        subset = [row for row in paired if row["season"] == season]
        ys = [row["y"] for row in subset]
        ms = score_probabilities(ys, [row["market"] for row in subset])
        cs = score_probabilities(ys, [row["candidate"] for row in subset])
        season_rows.append(
            {
                "variant": variant,
                "season": season,
                "n": len(subset),
                "delta_log_loss": cs["log_loss"] - ms["log_loss"],
                "delta_brier": cs["brier"] - ms["brier"],
            }
        )
    ece_delta = _ece(y, candidate) - _ece(y, market)
    summary = {
        "variant": variant,
        "n": len(paired),
        "coverage": 1.0,
        "delta_log_loss": candidate_score["log_loss"] - market_score["log_loss"],
        "log_loss_ci_low": boots["log_loss"]["ci_low"],
        "log_loss_ci_high": boots["log_loss"]["ci_high"],
        "log_loss_p": boots["log_loss"]["p_value"],
        "delta_brier": candidate_score["brier"] - market_score["brier"],
        "brier_ci_low": boots["brier"]["ci_low"],
        "brier_ci_high": boots["brier"]["ci_high"],
        "brier_p": boots["brier"]["p_value"],
        "delta_ece": ece_delta,
        "human_disposition": "",
    }
    season_ll = [row["delta_log_loss"] for row in season_rows]
    season_br = [row["delta_brier"] for row in season_rows]
    gates = {
        "aggregate_direction": summary["delta_log_loss"] < 0
        and summary["delta_brier"] < 0,
        "ci_below_zero": summary["log_loss_ci_high"] < 0
        and summary["brier_ci_high"] < 0,
        "materiality": summary["delta_log_loss"] <= -0.0005
        or summary["delta_brier"] <= -0.0002,
        "season_stability": sum(value <= 0 for value in season_ll) >= 3
        and sum(value < 0 for value in season_ll) >= 2
        and sum(value <= 0 for value in season_br) >= 3
        and sum(value < 0 for value in season_br) >= 2,
        "sample_size": len(paired) >= 2500
        and all(row["n"] >= 500 for row in season_rows),
        "paired_coverage": summary["coverage"] >= 0.95,
        "calibration": ece_delta <= 0.01,
    }
    summary["gate_results"] = json.dumps(gates, sort_keys=True)
    summary["eligible_for_human_review"] = all(gates.values())
    return summary, season_rows


def run_m20_study(
    matrix_path: Path, output_dir: Path, *, n_boot: int = 2000, seed: int = 20260904
) -> dict[str, Path]:
    variants = build_variants()
    fit_dir = output_dir / "fit"
    fit_residual_walkforward(
        matrix_path,
        fit_dir,
        protocol_version="2.0.0",
        matrix_schema_version=MATRIX_SCHEMA_VERSION,
        variants=variants,
    )
    predictions = _read(fit_dir / "predictions.csv")
    matrix_rows = _read(matrix_path)
    matrix = {int(row["game_id"]): row for row in matrix_rows}
    summaries = []
    seasons = []
    missingness_rows = []
    for variant in variants:
        if variant == "market_only":
            continue
        summary, season_rows = _evaluate_variant(
            variant, _paired(predictions, matrix, variant), n_boot=n_boot, seed=seed
        )
        summaries.append(summary)
        seasons.extend(season_rows)
        if variant.startswith("family__"):
            family = variant.removeprefix("family__")
            columns = CANDIDATE_FAMILIES[family]
            paired_rows = _paired(predictions, matrix, variant)
            for status in ("complete", "has_missing"):
                subset = [
                    row
                    for row in paired_rows
                    if (
                        all(matrix[row["game_id"]].get(col) not in (None, "") for col in columns)
                    )
                    == (status == "complete")
                ]
                if not subset:
                    continue
                ys = [row["y"] for row in subset]
                market_score = score_probabilities(ys, [row["market"] for row in subset])
                candidate_score = score_probabilities(
                    ys, [row["candidate"] for row in subset]
                )
                missingness_rows.append(
                    {
                        "variant": variant,
                        "source_status": status,
                        "n": len(subset),
                        "delta_log_loss": candidate_score["log_loss"]
                        - market_score["log_loss"],
                        "delta_brier": candidate_score["brier"]
                        - market_score["brier"],
                    }
                )

    for family in CANDIDATE_FAMILIES:
        singles = [
            row
            for row in summaries
            if row["variant"].startswith(f"single__{family}__")
        ]
        for metric in ("log_loss", "brier"):
            adjusted = holm_adjust([row[f"{metric}_p"] for row in singles])
            for row, correction in zip(singles, adjusted, strict=True):
                row[f"{metric}_holm_p"] = correction["holm_p"]
                row[f"{metric}_holm_reject"] = correction["reject"]

    compact = output_dir / "compact"
    summary_path = compact / "variant_summary.csv"
    season_path = compact / "season_stability.csv"
    coefficient_path = compact / "coefficient_stability.csv"
    missingness_path = compact / "missingness_sensitivity.csv"
    _write(summary_path, summaries)
    _write(season_path, seasons)
    coefficient_rows = []
    for bundle_path in sorted(fit_dir.glob("bundle_*.json")):
        bundle = json.loads(bundle_path.read_text())
        if bundle["variant"] == "market_only":
            continue
        for feature, coefficient in zip(
            bundle["feature_names"], bundle["beta"], strict=True
        ):
            coefficient_rows.append(
                {
                    "variant": bundle["variant"],
                    "fold_id": bundle["fold_id"],
                    "test_season": bundle["test_season"],
                    "transformed_feature": feature,
                    "coefficient": coefficient,
                }
            )
    _write(coefficient_path, coefficient_rows)
    _write(missingness_path, missingness_rows)
    packet = {
        "matrix_schema_version": MATRIX_SCHEMA_VERSION,
        "protocol_version": "2.0.0",
        "contains_2026_outcomes": False,
        "n_boot": n_boot,
        "families": {key: list(value) for key, value in CANDIDATE_FAMILIES.items()},
        "eligible_variants": [
            row["variant"] for row in summaries if row["eligible_for_human_review"]
        ],
        "human_dispositions": {},
        "status": "awaiting_human_dispositions",
    }
    packet_path = compact / "decision_packet.json"
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    return {
        "summary": summary_path,
        "seasons": season_path,
        "coefficients": coefficient_path,
        "missingness": missingness_path,
        "packet": packet_path,
    }


def main() -> None:
    parser = ArgumentParser(description="Run the predeclared M20 study")
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-boot", type=int, default=2000)
    args = parser.parse_args()
    run_m20_study(args.matrix, args.output, n_boot=args.n_boot)


if __name__ == "__main__":
    main()
