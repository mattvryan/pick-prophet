"""ESPN Pick'em slate import validation and conversion (no inferred membership)."""

from __future__ import annotations

import csv
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "game_id",
    "season",
    "week",
    "display_order",
    "is_pickem_game",
    "espn_home_pick_pct",
    "espn_expert_home_pct",
    "pct_captured_at",
    "captured_at",
    "source_url",
    "source_sha256",
    "tiebreaker_game_id",
    "espn_game_id",
    "match_status",
    "verification_status",
    "verifier_1",
    "verifier_2",
)

TRUE_VALUES = {"true", "1", "yes"}
FALSE_VALUES = {"false", "0", "no"}
CONFIRMED = "confirmed"
ALLOWED_STATUS = frozenset({"unverified", "single_source", CONFIRMED, "rejected"})
ALLOWED_MATCH_STATUS = frozenset(
    {"", "exact_id", "fallback_review", "unmatched"}
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass
class ImportValidation:
    ok: bool
    rows: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _parse_bool(value: str) -> bool | None:
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


def validate_pickem_import(
    path: Path,
    *,
    known_game_ids: set[int] | None = None,
) -> ImportValidation:
    """Validate a template-shaped Pick'em import without inventing membership."""

    result = ImportValidation(ok=True)
    if not path.exists():
        result.ok = False
        result.errors.append(f"file not found: {path}")
        return result

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            result.ok = False
            result.errors.append("CSV has no header row")
            return result
        headers = [h.strip() for h in reader.fieldnames]
        missing = [c for c in REQUIRED_COLUMNS if c not in headers]
        if missing:
            result.ok = False
            result.errors.append(f"missing required columns: {missing}")
            return result
        rows = list(reader)

    if not rows:
        result.ok = False
        result.errors.append("CSV has no data rows")
        return result

    seen_ids: set[int] = set()
    seen_positions: set[tuple[int, int, int]] = set()
    for index, row in enumerate(rows, start=2):
        prefix = f"row {index}"
        cleaned = {k: (row.get(k) or "").strip() for k in REQUIRED_COLUMNS}

        if _blank(cleaned["game_id"]):
            result.errors.append(f"{prefix}: game_id is required")
            continue
        try:
            game_id = int(cleaned["game_id"])
        except ValueError:
            result.errors.append(f"{prefix}: game_id must be an integer")
            continue
        if game_id in seen_ids:
            result.errors.append(f"{prefix}: duplicate game_id {game_id}")
        seen_ids.add(game_id)

        season_i: int | None = None
        week_i: int | None = None
        for field_name in ("season", "week"):
            if _blank(cleaned[field_name]):
                result.errors.append(f"{prefix}: {field_name} is required")
            else:
                try:
                    value = int(cleaned[field_name])
                except ValueError:
                    result.errors.append(f"{prefix}: {field_name} must be an integer")
                else:
                    if field_name == "season":
                        season_i = value
                    else:
                        week_i = value

        if not _blank(cleaned["display_order"]):
            try:
                display_order = int(cleaned["display_order"])
            except ValueError:
                result.errors.append(f"{prefix}: display_order must be an integer")
            else:
                if season_i is not None and week_i is not None:
                    key = (season_i, week_i, display_order)
                    if key in seen_positions:
                        result.errors.append(
                            f"{prefix}: duplicate display_order {display_order} "
                            f"for season {season_i} week {week_i}"
                        )
                    seen_positions.add(key)

        flag = _parse_bool(cleaned["is_pickem_game"])
        if flag is None:
            result.errors.append(
                f"{prefix}: is_pickem_game must be true/false "
                f"(got {cleaned['is_pickem_game']!r})"
            )

        if _blank(cleaned["captured_at"]):
            result.errors.append(f"{prefix}: captured_at provenance is required")
        if _blank(cleaned["source_url"]):
            result.errors.append(f"{prefix}: source_url provenance is required")

        if not _blank(cleaned["source_sha256"]) and not SHA256_RE.match(
            cleaned["source_sha256"]
        ):
            result.errors.append(f"{prefix}: source_sha256 must be 64 hex characters")

        match_status = cleaned["match_status"].lower()
        if match_status not in ALLOWED_MATCH_STATUS:
            result.errors.append(
                f"{prefix}: match_status must be one of "
                f"{sorted(s for s in ALLOWED_MATCH_STATUS if s)}"
                " or blank"
            )
        elif match_status == "fallback_review":
            result.warnings.append(
                f"{prefix}: match_status=fallback_review isolated for human review; "
                "not treated as verified membership"
            )
        elif match_status == "unmatched":
            result.warnings.append(
                f"{prefix}: unmatched game_id; membership not inferred"
            )

        if not _blank(cleaned["tiebreaker_game_id"]):
            try:
                int(cleaned["tiebreaker_game_id"])
            except ValueError:
                result.errors.append(f"{prefix}: tiebreaker_game_id must be an integer")

        status = cleaned["verification_status"].lower()
        cleaned["verification_status"] = status
        if status not in ALLOWED_STATUS:
            result.errors.append(
                f"{prefix}: verification_status must be one of {sorted(ALLOWED_STATUS)}"
            )
        elif status == CONFIRMED:
            if _blank(cleaned["verifier_1"]) or _blank(cleaned["verifier_2"]):
                result.errors.append(
                    f"{prefix}: confirmed rows require verifier_1 and verifier_2"
                )
            elif cleaned["verifier_1"].lower() == cleaned["verifier_2"].lower():
                result.errors.append(
                    f"{prefix}: confirmed rows need two distinct verifiers"
                )
            if _blank(cleaned["source_sha256"]):
                result.warnings.append(
                    f"{prefix}: confirmed rows should include source_sha256 "
                    "when a screenshot/export file exists"
                )
            if match_status in {"fallback_review", "unmatched"}:
                result.errors.append(
                    f"{prefix}: confirmed rows cannot use match_status={match_status}"
                )

        for pct_field in ("espn_home_pick_pct", "espn_expert_home_pct"):
            if _blank(cleaned[pct_field]):
                continue
            try:
                pct = float(cleaned[pct_field])
            except ValueError:
                result.errors.append(f"{prefix}: {pct_field} must be numeric")
                continue
            if not 0.0 <= pct <= 100.0:
                result.warnings.append(
                    f"{prefix}: {pct_field}={pct} outside 0–100; kept as transcribed"
                )

        if known_game_ids is not None and game_id not in known_game_ids:
            if match_status in {"", "exact_id"}:
                cleaned["match_status"] = "unmatched"
            result.warnings.append(
                f"{prefix}: game_id {game_id} not found in known game set "
                "(unmatched ID; membership not inferred)"
            )
        elif known_game_ids is not None and match_status in {"", "exact_id"}:
            cleaned["match_status"] = "exact_id"

        result.rows.append(cleaned)

    result.ok = not result.errors
    return result


def import_pickem_file(
    path: Path,
    destination: Path,
    *,
    known_game_ids: set[int] | None = None,
) -> Path:
    """Validate then copy into data/external/. Never invents slate membership."""

    result = validate_pickem_import(path, known_game_ids=known_game_ids)
    if not result.ok:
        raise ValueError("; ".join(result.errors))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing import: {destination}")
    shutil.copy2(path, destination)
    return destination


def slate_to_template_rows(slate_path: Path) -> list[dict[str, str]]:
    """Map a weekly operations slate.csv into template rows for forward seasons.

    Does not invent historical membership; only copies explicit weekly capture
    fields into the historical import contract shape.
    """

    with slate_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"slate has no header: {slate_path}")
        rows = list(reader)

    output: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=2):
        game_id = (row.get("cfbd_game_id") or "").strip()
        if not game_id:
            raise ValueError(f"slate row {index}: cfbd_game_id is required")
        home_pct = (row.get("home_public_pick_pct") or "").strip()
        captured = (row.get("captured_at_utc") or "").strip()
        output.append(
            {
                "game_id": game_id,
                "season": (row.get("season") or "").strip(),
                "week": (row.get("contest_week") or row.get("week") or "").strip(),
                "display_order": (row.get("display_order") or "").strip(),
                "is_pickem_game": "true",
                "espn_home_pick_pct": home_pct,
                "espn_expert_home_pct": "",
                "pct_captured_at": captured,
                "captured_at": captured,
                "source_url": (row.get("source") or "").strip(),
                "source_sha256": "",
                "tiebreaker_game_id": "",
                "espn_game_id": (row.get("espn_game_id") or "").strip(),
                "match_status": "exact_id" if game_id else "unmatched",
                "verification_status": "unverified",
                "verifier_1": "",
                "verifier_2": "",
            }
        )
    return output


def write_template_csv(rows: list[dict[str, str]], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in REQUIRED_COLUMNS})
    return output


def load_known_game_ids(processed_csv: Path) -> set[int]:
    ids: set[int] = set()
    with processed_csv.open(newline="") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("game_id") or "").strip()
            if raw:
                ids.add(int(raw))
    return ids
