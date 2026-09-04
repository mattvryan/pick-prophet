"""Verified ESPN Pick'em sampling-frame registry (no inferred membership)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pickem import (
    CONFIRMED,
    REQUIRED_COLUMNS,
    validate_pickem_import,
    write_template_csv,
)

SAMPLING_ALL_FBS = "all_fbs"
SAMPLING_VERIFIED = "verified_espn_pickem"


@dataclass
class RegistryBuild:
    rows: list[dict[str, str]] = field(default_factory=list)
    fallback_review: list[dict[str, str]] = field(default_factory=list)
    unmatched: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def sampling_frame_label(
    *,
    is_pickem_game: bool | None,
    verification_status: str | None,
    match_status: str | None = None,
) -> str:
    """Explicit frame labels used by evaluation artifacts."""

    status = str(verification_status or "").strip().lower()
    match = str(match_status or "").strip().lower()
    if match in {"fallback_review", "unmatched"}:
        return SAMPLING_ALL_FBS
    if is_pickem_game is True and status == CONFIRMED and match in {"", "exact_id"}:
        return SAMPLING_VERIFIED
    return SAMPLING_ALL_FBS


def build_registry(
    import_paths: list[Path],
    *,
    known_game_ids: set[int] | None = None,
) -> RegistryBuild:
    """Merge validated imports into a registry keyed by stable CFBD game_id."""

    result = RegistryBuild()
    by_id: dict[int, dict[str, str]] = {}
    for path in import_paths:
        result.sources.append(str(path))
        validation = validate_pickem_import(path, known_game_ids=known_game_ids)
        result.warnings.extend(f"{path.name}: {w}" for w in validation.warnings)
        if not validation.ok:
            result.errors.extend(f"{path.name}: {e}" for e in validation.errors)
            continue
        for row in validation.rows:
            game_id = int(row["game_id"])
            match_status = (row.get("match_status") or "").lower()
            if match_status == "fallback_review":
                result.fallback_review.append(row)
                continue
            if match_status == "unmatched":
                result.unmatched.append(row)
                continue
            if game_id in by_id:
                result.errors.append(
                    f"duplicate game_id {game_id} across registry sources "
                    f"({by_id[game_id].get('_source')} vs {path.name})"
                )
                continue
            payload = dict(row)
            payload["_source"] = path.name
            payload["sampling_frame"] = sampling_frame_label(
                is_pickem_game=row.get("is_pickem_game", "").lower() == "true",
                verification_status=row.get("verification_status"),
                match_status=match_status,
            )
            by_id[game_id] = payload

    result.rows = sorted(by_id.values(), key=lambda r: int(r["game_id"]))
    return result


def write_registry(
    registry: RegistryBuild,
    output_dir: Path,
) -> dict[str, Path]:
    """Write registry CSV plus isolated fallback/unmatched review tables."""

    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "pickem_registry.csv"
    fieldnames = list(REQUIRED_COLUMNS) + ["sampling_frame", "_source"]
    with registry_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in registry.rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    fallback_path = output_dir / "pickem_fallback_review.csv"
    write_template_csv(registry.fallback_review, fallback_path)

    unmatched_path = output_dir / "pickem_unmatched.csv"
    write_template_csv(registry.unmatched, unmatched_path)

    manifest = {
        "built_at": datetime.now(UTC).isoformat(),
        "sources": registry.sources,
        "registry_rows": len(registry.rows),
        "verified_espn_pickem_rows": sum(
            1
            for row in registry.rows
            if row.get("sampling_frame") == SAMPLING_VERIFIED
        ),
        "fallback_review_rows": len(registry.fallback_review),
        "unmatched_rows": len(registry.unmatched),
        "errors": registry.errors,
        "warnings": registry.warnings,
        "policy": (
            "Never infer ESPN membership from rankings, TV, or prominence. "
            "Only exact_id joins with verification_status=confirmed enter "
            f"{SAMPLING_VERIFIED}."
        ),
    }
    manifest_path = output_dir / "pickem_registry_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "registry": registry_path,
        "fallback_review": fallback_path,
        "unmatched": unmatched_path,
        "manifest": manifest_path,
    }


def apply_registry_labels(
    game_rows: list[dict[str, Any]],
    registry_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Stamp sampling_frame / verification fields onto canonical game rows."""

    by_id = {int(row["game_id"]): row for row in registry_rows}
    for row in game_rows:
        game_id = int(row["game_id"])
        match = by_id.get(game_id)
        if match is None:
            row["sampling_frame"] = SAMPLING_ALL_FBS
            row.setdefault("verification_status", None)
            row.setdefault("is_pickem_game", None)
            continue
        row["is_pickem_game"] = match.get("is_pickem_game", "").lower() == "true"
        row["verification_status"] = match.get("verification_status")
        row["match_status"] = match.get("match_status")
        row["sampling_frame"] = match.get("sampling_frame") or sampling_frame_label(
            is_pickem_game=row["is_pickem_game"],
            verification_status=row["verification_status"],
            match_status=row.get("match_status"),
        )
        for field_name in ("espn_home_pick_pct", "espn_expert_home_pct"):
            raw = match.get(field_name)
            row[field_name] = float(raw) if raw not in (None, "") else None
    return game_rows


def unrecoverable_weeks_report(
    *,
    research_seasons: list[int],
    recovered: set[tuple[int, int]],
    contest_weeks_by_season: dict[int, list[int]] | None = None,
) -> dict[str, Any]:
    """List season/weeks with no verified archive evidence.

    ``contest_weeks_by_season`` defaults to weeks 1–15 for each research season
    as a search checklist span—not a claim that ESPN ran those contests.
    """

    weeks_by_season = contest_weeks_by_season or {
        season: list(range(1, 16)) for season in research_seasons
    }
    missing: list[dict[str, int]] = []
    for season in research_seasons:
        for week in weeks_by_season.get(season, []):
            if (season, week) not in recovered:
                missing.append({"season": season, "week": week})
    return {
        "research_seasons": research_seasons,
        "recovered_season_weeks": sorted(
            [{"season": s, "week": w} for s, w in recovered],
            key=lambda item: (item["season"], item["week"]),
        ),
        "unrecoverable_or_unsearched_season_weeks": missing,
        "note": (
            "Absence from this list does not invent membership; it only tracks "
            "where verified archive evidence has not yet been registered."
        ),
    }
