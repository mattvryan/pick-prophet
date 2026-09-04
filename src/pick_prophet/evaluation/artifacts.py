"""Stable prediction and summary artifact writers for evaluation runs."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

PREDICTION_COLUMNS = (
    "protocol_version",
    "model",
    "fold_id",
    "test_season",
    "game_id",
    "week",
    "y_true",
    "p_home",
    "sampling_frame",
)


def write_predictions(
    rows: Sequence[dict[str, Any]],
    path: Path,
    *,
    protocol_version: str,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PREDICTION_COLUMNS))
        writer.writeheader()
        for row in rows:
            payload = {key: row.get(key) for key in PREDICTION_COLUMNS}
            payload["protocol_version"] = protocol_version
            writer.writerow(payload)
    return path


def write_summary(summary: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return path


def sampling_frame_for_row(row: dict[str, Any] | Any) -> str:
    """Label all-FBS vs confirmed Pick'em without inventing membership."""

    from pick_prophet.features.pickem_registry import sampling_frame_label

    if isinstance(row, dict):
        if row.get("sampling_frame") in {"all_fbs", "verified_espn_pickem"}:
            return str(row["sampling_frame"])
        flag = row.get("is_pickem_game")
        status = row.get("verification_status")
        match_status = row.get("match_status")
    else:
        existing = getattr(row, "sampling_frame", None)
        if existing in {"all_fbs", "verified_espn_pickem"}:
            return str(existing)
        flag = getattr(row, "is_pickem_game", None)
        status = getattr(row, "verification_status", None)
        match_status = getattr(row, "match_status", None)
    is_pickem = flag is True or str(flag).strip().lower() == "true"
    return sampling_frame_label(
        is_pickem_game=is_pickem,
        verification_status=str(status) if status is not None else None,
        match_status=str(match_status) if match_status is not None else None,
    )


def iter_prediction_rows(
    *,
    protocol_version: str,
    model: str,
    fold_id: str,
    test_season: int,
    game_ids: Iterable[Any],
    weeks: Iterable[Any],
    y_true: Iterable[Any],
    p_home: Iterable[float],
    sampling_frames: Iterable[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for game_id, week, y, p, frame in zip(
        game_ids, weeks, y_true, p_home, sampling_frames, strict=True
    ):
        rows.append(
            {
                "protocol_version": protocol_version,
                "model": model,
                "fold_id": fold_id,
                "test_season": test_season,
                "game_id": int(game_id),
                "week": int(week) if week is not None and str(week) != "" else "",
                "y_true": int(y),
                "p_home": float(p),
                "sampling_frame": frame,
            }
        )
    return rows
