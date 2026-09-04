"""Validation for M15 historical Pick'em source candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = {"candidate_single_source", "confirmed", "rejected"}


def validate_source_inventory(payload: dict[str, Any]) -> None:
    if payload.get("artifact_version") != "1.0.0":
        raise ValueError("unsupported M15 artifact version")
    rows = payload.get("week_candidates")
    if not isinstance(rows, list):
        raise TypeError("week_candidates must be a list")
    seen: set[tuple[int, int]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("candidate rows must be objects")
        key = (int(row["season"]), int(row["week"]))
        if key in seen:
            raise ValueError(f"duplicate season/week candidate: {key}")
        seen.add(key)
        status = row.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"invalid source status: {status}")
        sources = row.get("sources", [])
        if not isinstance(sources, list):
            raise TypeError("sources must be a list")
        source_ids = {source.get("source_id") for source in sources}
        if None in source_ids or len(source_ids) != len(sources):
            raise ValueError(f"source IDs must be nonempty and distinct: {key}")
        if status == "confirmed":
            if len(source_ids) < 2:
                raise ValueError(f"confirmed week requires two sources: {key}")
            if not row.get("pre_lock_provenance_verified"):
                raise ValueError(f"confirmed week requires pre-lock provenance: {key}")
            if int(row.get("canonical_game_ids_verified", 0)) <= 0:
                raise ValueError(f"confirmed week requires canonical game IDs: {key}")


def load_and_validate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise TypeError("M15 inventory must be a JSON object")
    validate_source_inventory(payload)
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
