"""M10 ablation and robustness runner over the M08 residual stack."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pick_prophet.evaluation.cluster_bootstrap import (
    bootstrap_paired_delta_clusters,
    cluster_keys,
)
from pick_prophet.evaluation.metrics import score_probabilities
from pick_prophet.evaluation.protocol import load_protocol
from pick_prophet.models.residual_ablation_variants import (
    ANOMALOUS_SEASONS,
    FAMILIES,
    FAMILIES_DECLARED,
    MIN_ESPN_N,
    UNAVAILABLE_FOR_EVIDENCE,
    assert_ablation_variants_valid,
    build_ablation_variants,
)
from pick_prophet.models.residual_diagnostics import fit_calibration_glm
from pick_prophet.models.residual_fit import fit_residual_walkforward, load_matrix_rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _as_int(value: Any) -> int:
    return int(float(value))


def _favorite_band(spread: Any) -> str:
    import math

    if spread is None or spread == "":
        return "missing_spread"
    try:
        magnitude = abs(float(spread))
    except (TypeError, ValueError):
        return "missing_spread"
    if math.isnan(magnitude):
        return "missing_spread"
    if magnitude < 3:
        return "lt_3"
    if magnitude <= 7:
        return "3_to_7"
    return "gt_7"


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _pair_rows(
    preds: Sequence[dict[str, Any]], candidate: str
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in preds:
        key = (str(row["fold_id"]), _as_int(row["game_id"]))
        by_key[key][str(row["model"])] = row
    cand_ids = {
        (str(r["fold_id"]), _as_int(r["game_id"]))
        for r in preds
        if str(r["model"]) == candidate
    }
    market_ids = {
        (str(r["fold_id"]), _as_int(r["game_id"]))
        for r in preds
        if str(r["model"]) == "market_only"
    }
    if cand_ids != market_ids:
        raise ValueError(f"unequal paired game IDs for {candidate}")
    paired: list[dict[str, Any]] = []
    for key, models in sorted(by_key.items()):
        if candidate not in models or "market_only" not in models:
            raise ValueError(f"missing market_only or {candidate} for {key}")
        market = models["market_only"]
        cand = models[candidate]
        paired.append(
            {
                **cand,
                "p_market": float(market["p_home"]),
                "p_candidate": float(cand["p_home"]),
                "y_true": _as_int(cand["y_true"]),
                "test_season": _as_int(cand["test_season"]),
                "week": _as_int(cand["week"]),
            }
        )
    return paired


def season_drop_metrics(
    paired: Sequence[dict[str, Any]],
    *,
    drop_season: int,
) -> dict[str, Any]:
    """Re-aggregate existing walk-forward pairs after dropping a held-out season.

    This is not a retrain; training windows are unchanged.
    """

    kept = [r for r in paired if int(r["test_season"]) != int(drop_season)]
    if not kept:
        return {
            "drop_season": drop_season,
            "mode": "aggregate_existing_predictions",
            "retrain": False,
            "n": 0,
            "status": "empty",
        }
    m_c = score_probabilities(
        [int(r["y_true"]) for r in kept], [float(r["p_candidate"]) for r in kept]
    )
    m_m = score_probabilities(
        [int(r["y_true"]) for r in kept], [float(r["p_market"]) for r in kept]
    )
    return {
        "drop_season": drop_season,
        "mode": "aggregate_existing_predictions",
        "retrain": False,
        "n": m_c["n"],
        "status": "ok",
        "log_loss": m_c["log_loss"],
        "brier": m_c["brier"],
        "accuracy": m_c["accuracy"],
        "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
        "delta_brier": m_c["brier"] - m_m["brier"],
        "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
    }


def _enrich_from_matrix(
    paired: list[dict[str, Any]], matrix_rows: Sequence[dict[str, Any]]
) -> None:
    by_id = {_as_int(r["game_id"]): r for r in matrix_rows}
    for row in paired:
        m = by_id[_as_int(row["game_id"])]
        row["season_type"] = str(m.get("season_type") or "regular")
        row["neutral_site"] = m.get("neutral_site")
        row["spread_home"] = m.get("spread_home")
        row["home_conference"] = m.get("home_conference")
        row["_favorite_band"] = _favorite_band(m.get("spread_home"))
        row["sampling_frame"] = (
            m.get("sampling_frame")
            or row.get("sampling_frame")
            or "all_fbs"
        )


def _slice_rows(paired: Sequence[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    if name == "overall":
        return list(paired)
    if name == "weeks_1_3":
        return [r for r in paired if 1 <= int(r["week"]) <= 3]
    if name == "weeks_4_plus":
        return [r for r in paired if int(r["week"]) >= 4]
    if name == "neutral_site":
        return [r for r in paired if _truthy(r.get("neutral_site"))]
    if name == "non_neutral":
        return [r for r in paired if not _truthy(r.get("neutral_site"))]
    if name.startswith("favorite_"):
        band = name.removeprefix("favorite_")
        return [r for r in paired if r.get("_favorite_band") == band]
    if name == "verified_espn_pickem":
        return [r for r in paired if r.get("sampling_frame") == "verified_espn_pickem"]
    if name.startswith("home_conference__"):
        conf = name.removeprefix("home_conference__")
        return [r for r in paired if str(r.get("home_conference")) == conf]
    raise ValueError(f"unknown slice {name!r}")


def _unit_type(variant: str) -> str:
    if variant == "market_only":
        return "baseline"
    if variant.startswith("single__"):
        return "single_feature"
    if variant.startswith("family__"):
        return "family"
    if variant.startswith("lof__"):
        return "leave_family_out"
    if variant == "combined":
        return "combined"
    return "other"


def run_ablation(
    matrix_path: Path,
    out_dir: Path,
    *,
    protocol_version: str = "1.0.0",
    matrix_schema_version: str = "1.0.0",
    variants: dict[str, tuple[str, ...]] | None = None,
    n_boot: int | None = None,
    enforce_protocol_n_boot: bool = True,
    write_report_path: Path | None = None,
    held_out_inference_note: str | None = None,
) -> dict[str, Path]:
    """Fit ablation variants and write compact evidence; never set recommendations."""

    active = variants if variants is not None else build_ablation_variants()
    assert_ablation_variants_valid(active)
    protocol = load_protocol(protocol_version)
    if enforce_protocol_n_boot:
        if n_boot is not None and int(n_boot) != int(protocol.n_boot):
            raise ValueError(
                f"n_boot={n_boot} does not match protocol n_boot={protocol.n_boot}; "
                "pass enforce_protocol_n_boot=False only for tests"
            )
        boot_n = int(protocol.n_boot)
    else:
        boot_n = int(protocol.n_boot if n_boot is None else n_boot)
    seed = protocol.bootstrap_seed
    out_dir = Path(out_dir)
    fit_dir = out_dir / "fit"
    compact = out_dir / "compact"
    compact.mkdir(parents=True, exist_ok=True)

    inference_note = held_out_inference_note or (
        "INFERENCE WINDOW: residual ablation proper-score evidence covers held-out "
        "seasons 2022–2025 only (moneyline/implied coverage; earlier expanding "
        "folds skipped when train/test eligible sets are empty). "
        "2020 anomalous-season sensitivity cannot be evaluated in this pull "
        "(no eligible held-out predictions for 2020)."
    )

    fit_residual_walkforward(
        matrix_path,
        fit_dir,
        protocol_version=protocol_version,
        matrix_schema_version=matrix_schema_version,
        variants=active,
    )

    preds = _read_csv(fit_dir / "predictions.csv")
    details = _read_csv(fit_dir / "residual_details.csv")
    matrix_rows = load_matrix_rows(matrix_path)
    candidates = [v for v in active if v != "market_only"]

    registry = {
        "variants": {k: list(v) for k, v in active.items()},
        "families": {k: list(v) for k, v in FAMILIES.items()},
        "families_declared": {k: list(v) for k, v in FAMILIES_DECLARED.items()},
        "unavailable_for_evidence": sorted(UNAVAILABLE_FOR_EVIDENCE),
        "unavailable_reason": (
            "Opening/movement fields are structurally missing under CFBD "
            "historical timing and are excluded from family evidence and M11 "
            "eligibility."
        ),
        "min_espn_n": MIN_ESPN_N,
        "anomalous_seasons": list(ANOMALOUS_SEASONS),
        "protocol_version": protocol.protocol_version,
        "n_boot": boot_n,
        "bootstrap_seed": seed,
        "inference_window_note": inference_note,
    }
    registry_path = compact / "ablation_registry.json"
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")

    overall_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    boot_rows: list[dict[str, Any]] = []
    slice_rows_out: list[dict[str, Any]] = []
    season_drop_rows: list[dict[str, Any]] = []
    anomalous_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    worksheet_rows: list[dict[str, Any]] = []

    # Coverage from eligibility counts
    elig = _read_csv(fit_dir / "eligibility.csv")
    for row in elig:
        if row.get("reason_code") == "counts":
            coverage_rows.append({**row, "source": "eligibility_counts"})

    detail_adj: dict[tuple[str, str, int], float] = {}
    for row in details:
        key = (str(row["model"]), str(row["fold_id"]), _as_int(row["game_id"]))
        detail_adj[key] = float(row.get("adjustment") or 0.0)

    slice_names = [
        "overall",
        "weeks_1_3",
        "weeks_4_plus",
        "neutral_site",
        "non_neutral",
        "favorite_lt_3",
        "favorite_3_to_7",
        "favorite_gt_7",
        "favorite_missing_spread",
        "verified_espn_pickem",
    ]

    for candidate in candidates:
        paired = _pair_rows(preds, candidate)
        _enrich_from_matrix(paired, matrix_rows)

        # Missingness proxy: fraction of rows with zero adjustment when variant
        # has columns (market signal only) — also count empty source fields on matrix
        cols = active[candidate]
        miss_rates = []
        for col in cols:
            missing = 0
            for row in paired:
                m = next(r for r in matrix_rows if _as_int(r["game_id"]) == _as_int(row["game_id"]))
                if m.get(col) in (None, ""):
                    missing += 1
            miss_rates.append(
                {
                    "variant": candidate,
                    "column": col,
                    "missing_rate": missing / len(paired) if paired else 0.0,
                    "n": len(paired),
                }
            )
        coverage_rows.extend(miss_rates)

        m_c = score_probabilities(
            [r["y_true"] for r in paired], [r["p_candidate"] for r in paired]
        )
        m_m = score_probabilities(
            [r["y_true"] for r in paired], [r["p_market"] for r in paired]
        )
        overall_rows.append(
            {
                "variant": candidate,
                "n": m_c["n"],
                "log_loss": m_c["log_loss"],
                "brier": m_c["brier"],
                "accuracy": m_c["accuracy"],
                "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
                "delta_brier": m_c["brier"] - m_m["brier"],
                "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
            }
        )

        folds = sorted({str(r["fold_id"]) for r in paired})
        for fold in folds:
            subset = [r for r in paired if str(r["fold_id"]) == fold]
            mc = score_probabilities(
                [r["y_true"] for r in subset], [r["p_candidate"] for r in subset]
            )
            mm = score_probabilities(
                [r["y_true"] for r in subset], [r["p_market"] for r in subset]
            )
            fold_rows.append(
                {
                    "variant": candidate,
                    "fold_id": fold,
                    "test_season": subset[0]["test_season"],
                    "n": mc["n"],
                    "delta_log_loss": mc["log_loss"] - mm["log_loss"],
                    "delta_brier": mc["brier"] - mm["brier"],
                    "delta_accuracy": mc["accuracy"] - mm["accuracy"],
                }
            )

        clusters = cluster_keys(
            [r["test_season"] for r in paired],
            [r["season_type"] for r in paired],
            [r["week"] for r in paired],
        )
        for metric in ("log_loss", "brier"):
            boot = bootstrap_paired_delta_clusters(
                clusters,
                [r["y_true"] for r in paired],
                [r["p_market"] for r in paired],
                [r["p_candidate"] for r in paired],
                metric=metric,
                n_boot=boot_n,
                seed=protocol.bootstrap_seed,
                contrast_id=f"{candidate}|overall|{metric}",
            )
            boot_rows.append({"variant": candidate, "slice": "overall", **boot})

        cal = fit_calibration_glm(
            [r["y_true"] for r in paired], [r["p_candidate"] for r in paired]
        )
        calibration_rows.append({"variant": candidate, "scope": "aggregate", **cal})

        # Conference slices: top conferences by count (bounded)
        conf_counts: dict[str, int] = defaultdict(int)
        for r in paired:
            conf_counts[str(r.get("home_conference") or "")] += 1
        top_confs = sorted(conf_counts, key=lambda c: (-conf_counts[c], c))[:3]
        local_slices = list(slice_names) + [f"home_conference__{c}" for c in top_confs if c]

        for slice_name in local_slices:
            subset = _slice_rows(paired, slice_name)
            n = len(subset)
            status = "ok"
            if n == 0:
                status = "empty"
            elif slice_name == "verified_espn_pickem" and n < MIN_ESPN_N:
                status = "insufficient"
            row_out: dict[str, Any] = {
                "variant": candidate,
                "slice": slice_name,
                "n": n,
                "status": status,
            }
            if status == "ok":
                mc = score_probabilities(
                    [r["y_true"] for r in subset], [r["p_candidate"] for r in subset]
                )
                mm = score_probabilities(
                    [r["y_true"] for r in subset], [r["p_market"] for r in subset]
                )
                row_out.update(
                    {
                        "delta_log_loss": mc["log_loss"] - mm["log_loss"],
                        "delta_brier": mc["brier"] - mm["brier"],
                        "delta_accuracy": mc["accuracy"] - mm["accuracy"],
                    }
                )
            else:
                row_out.update(
                    {
                        "delta_log_loss": "",
                        "delta_brier": "",
                        "delta_accuracy": "",
                    }
                )
            slice_rows_out.append(row_out)

        seasons = sorted({int(r["test_season"]) for r in paired})
        for season in seasons:
            drop = season_drop_metrics(paired, drop_season=season)
            season_drop_rows.append({"variant": candidate, **drop})

        for season in ANOMALOUS_SEASONS:
            with_s = [r for r in paired if int(r["test_season"]) == season]
            if not with_s:
                anomalous_rows.append(
                    {
                        "variant": candidate,
                        "anomalous_season": season,
                        "view": "season_sensitivity",
                        "retrain": False,
                        "n": 0,
                        "status": "not_available",
                        "reason": "no_held_out_predictions_for_anomalous_season",
                        "delta_log_loss": "",
                        "delta_brier": "",
                        "delta_accuracy": "",
                        "log_loss": "",
                        "brier": "",
                        "accuracy": "",
                        "mode": "not_evaluated",
                    }
                )
                continue
            mc = score_probabilities(
                [r["y_true"] for r in with_s], [r["p_candidate"] for r in with_s]
            )
            mm = score_probabilities(
                [r["y_true"] for r in with_s], [r["p_market"] for r in with_s]
            )
            anomalous_rows.append(
                {
                    "variant": candidate,
                    "anomalous_season": season,
                    "view": "season_only",
                    "retrain": False,
                    "n": mc["n"],
                    "status": "ok",
                    "reason": "",
                    "delta_log_loss": mc["log_loss"] - mm["log_loss"],
                    "delta_brier": mc["brier"] - mm["brier"],
                    "delta_accuracy": mc["accuracy"] - mm["accuracy"],
                }
            )
            without = season_drop_metrics(paired, drop_season=season)
            anomalous_rows.append(
                {
                    "variant": candidate,
                    "anomalous_season": season,
                    "view": "exclude_held_out_season",
                    "status": without.get("status", "ok"),
                    "reason": "",
                    **{k: without[k] for k in without if k != "drop_season"},
                }
            )

        # Worksheet row for human review
        ll_boot = next(b for b in boot_rows if b["variant"] == candidate and b["metric"] == "log_loss")
        worksheet_rows.append(
            {
                "unit_type": _unit_type(candidate),
                "unit_id": candidate,
                "n": m_c["n"],
                "delta_log_loss": m_c["log_loss"] - m_m["log_loss"],
                "delta_brier": m_c["brier"] - m_m["brier"],
                "delta_accuracy": m_c["accuracy"] - m_m["accuracy"],
                "log_loss_ci_low": ll_boot["ci_low"],
                "log_loss_ci_high": ll_boot["ci_high"],
                "calibration_status": cal["status"],
                "recommendation": "",
                "reviewer": "",
                "review_notes": "",
            }
        )

    paths: dict[str, Path] = {"ablation_registry": registry_path}
    specs = [
        (
            "overall_metrics",
            overall_rows,
            [
                "variant",
                "n",
                "log_loss",
                "brier",
                "accuracy",
                "delta_log_loss",
                "delta_brier",
                "delta_accuracy",
            ],
        ),
        (
            "fold_metrics",
            fold_rows,
            [
                "variant",
                "fold_id",
                "test_season",
                "n",
                "delta_log_loss",
                "delta_brier",
                "delta_accuracy",
            ],
        ),
        (
            "paired_bootstrap",
            boot_rows,
            [
                "variant",
                "slice",
                "metric",
                "contrast_id",
                "delta",
                "mean_delta",
                "ci_low",
                "ci_high",
                "p_value",
                "n_boot",
                "seed",
                "n_clusters",
                "n_rows",
            ],
        ),
        (
            "slice_metrics",
            slice_rows_out,
            [
                "variant",
                "slice",
                "n",
                "status",
                "delta_log_loss",
                "delta_brier",
                "delta_accuracy",
            ],
        ),
        (
            "season_drop",
            season_drop_rows,
            [
                "variant",
                "drop_season",
                "mode",
                "retrain",
                "n",
                "status",
                "log_loss",
                "brier",
                "accuracy",
                "delta_log_loss",
                "delta_brier",
                "delta_accuracy",
            ],
        ),
        (
            "anomalous_season",
            anomalous_rows,
            [
                "variant",
                "anomalous_season",
                "view",
                "retrain",
                "n",
                "status",
                "reason",
                "delta_log_loss",
                "delta_brier",
                "log_loss",
                "brier",
                "accuracy",
                "delta_accuracy",
                "mode",
            ],
        ),
        (
            "calibration_summary",
            calibration_rows,
            [
                "variant",
                "scope",
                "n",
                "eps",
                "a",
                "b",
                "a_ideal",
                "b_ideal",
                "status",
                "reason",
                "nit",
            ],
        ),
        (
            "coverage_missingness",
            coverage_rows,
            [
                "variant",
                "column",
                "missing_rate",
                "n",
                "fold_id",
                "split",
                "reason_code",
                "input_rows",
                "eligible_rows",
                "excluded_rows",
                "source",
                "game_id",
            ],
        ),
        (
            "decision_worksheet",
            worksheet_rows,
            [
                "unit_type",
                "unit_id",
                "n",
                "delta_log_loss",
                "delta_brier",
                "delta_accuracy",
                "log_loss_ci_low",
                "log_loss_ci_high",
                "calibration_status",
                "recommendation",
                "reviewer",
                "review_notes",
            ],
        ),
    ]
    for name, rows, fields in specs:
        path = compact / f"{name}.csv"
        _write_csv(path, rows, fields)
        paths[name] = path

    report_path = write_report_path or (compact / "incremental_value_report.md")
    lines = [
        "# Incremental value report (M10)",
        "",
        f"**{inference_note}**",
        "",
        "Evidence from the M08 fixed-offset residual ablation runner.",
        "Large row-level fit artifacts are not committed; see compact CSVs.",
        "",
        f"- Bootstrap: n_boot={boot_n} (protocol), seed={seed}",
        (
            "- Structurally unavailable (excluded from evidence/M11 eligibility): "
            + ", ".join(sorted(UNAVAILABLE_FOR_EVIDENCE))
        ),
        "",
        "## Hard rules",
        "",
        "- Comparisons reuse M08 fitting; no new model family or HP search.",
        "- Season-drop rows are **aggregations of existing held-out predictions**, not retrains.",
        "- Decision labels (`promote` / `review_only` / `reject`) are **human-only**;",
        "  `decision_worksheet.csv` leaves `recommendation` unset.",
        "- Do not treat an unavailable anomalous season as a successful exclusion contrast.",
        "",
        "## Aggregate deltas vs market_only",
        "",
    ]
    for row in overall_rows:
        lines.append(
            f"- `{row['variant']}`: n={row['n']}, "
            f"Δlog_loss={row['delta_log_loss']}, Δbrier={row['delta_brier']}"
        )
    lines.extend(
        [
            "",
            "## Human review",
            "",
            "Fill `recommendation` in `decision_worksheet.csv` after reviewing",
            "fold consistency, bootstrap CIs, calibration, missingness, season-drop,",
            "and anomalous-season (2020) tables. Do not treat accuracy alone as promotion evidence.",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))
    paths["report"] = report_path
    return paths
