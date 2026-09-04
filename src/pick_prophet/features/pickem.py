"""ESPN Pick'em slate import validation and conversion (no inferred membership)."""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "game_id",
    "season",
    "week",
    "is_pickem_game",
    "espn_home_pick_pct",
    "espn_expert_home_pct",
    "captured_at",
    "source_url",
    "verification_status",
    "verifier_1",
    "verifier_2",
)

TRUE_VALUES = {"true", "1", "yes"}
FALSE_VALUES = {"false", "0", "no"}
CONFIRMED = "confirmed"
ALLOWED_STATUS = frozenset({"unverified", "single_source", CONFIRMED, "rejected"})


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

    seen: set[int] = set()
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
        if game_id in seen:
            result.errors.append(f"{prefix}: duplicate game_id {game_id}")
        seen.add(game_id)

        for field_name in ("season", "week"):
            if _blank(cleaned[field_name]):
                result.errors.append(f"{prefix}: {field_name} is required")
            else:
                try:
                    int(cleaned[field_name])
                except ValueError:
                    result.errors.append(f"{prefix}: {field_name} must be an integer")

        flag = _parse_bool(cleaned["is_pickem_game"])
        if flag is None:
            result.errors.append(
                f"{prefix}: is_pickem_game must be true/false (got {cleaned['is_pickem_game']!r})"
            )

        if _blank(cleaned["captured_at"]):
            result.errors.append(f"{prefix}: captured_at provenance is required")
        if _blank(cleaned["source_url"]):
            result.errors.append(f"{prefix}: source_url provenance is required")

        status = cleaned["verification_status"].lower()
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
            result.warnings.append(
                f"{prefix}: game_id {game_id} not found in known game set "
                "(unmatched ID; membership not inferred)"
            )

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
        output.append(
            {
                "game_id": game_id,
                "season": (row.get("season") or "").strip(),
                "week": (row.get("contest_week") or row.get("week") or "").strip(),
                "is_pickem_game": "true",
                "espn_home_pick_pct": home_pct,
                "espn_expert_home_pct": "",
                "captured_at": (row.get("captured_at_utc") or "").strip(),
                "source_url": (row.get("source") or "").strip(),
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
        writer.writerows(rows)
    return output


def load_known_game_ids(processed_csv: Path) -> set[int]:
    ids: set[int] = set()
    with processed_csv.open(newline="") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("game_id") or "").strip()
            if raw:
                ids.add(int(raw))
    return ids
