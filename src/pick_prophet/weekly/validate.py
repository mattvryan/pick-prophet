"""Weekly slate validation."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PUBLIC_PCT_TOLERANCE = 0.51


@dataclass
class ValidationResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_timestamp(value: str, field_name: str, row_label: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{row_label}: malformed {field_name} {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{row_label}: {field_name} must be timezone-aware ISO-8601")
    return parsed.astimezone(UTC)


def parse_optional_float(value: str) -> float | None:
    text = (value or "").strip()
    if text == "":
        return None
    return float(text)


def parse_moneyline(value: str, field_name: str, row_label: str) -> float | None:
    text = (value or "").strip()
    if text == "":
        return None
    try:
        odds = float(text)
    except ValueError as exc:
        raise ValueError(
            f"{row_label}: {field_name} must be numeric, got {value!r}"
        ) from exc
    if odds == 0:
        raise ValueError(f"{row_label}: {field_name} must be nonzero")
    if -100 < odds < 100:
        raise ValueError(
            f"{row_label}: {field_name}={odds} is invalid; American odds "
            "cannot fall strictly between -100 and +100"
        )
    return odds


def parse_boolean(value: str, field_name: str, row_label: str) -> bool:
    text = (value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ValueError(f"{row_label}: {field_name} must be a boolean, got {value!r}")


def _row_label(row_number: int, display_order: str | None) -> str:
    if display_order:
        return f"row {row_number} (display_order={display_order})"
    return f"row {row_number}"


def validate_slate(
    path: Path | str,
    *,
    as_of: str | None = None,
) -> ValidationResult:
    """Validate a weekly slate CSV. Errors fail; warnings are advisory."""

    path = Path(path)
    result = ValidationResult()
    if not path.exists():
        result.errors.append(f"slate not found: {path}")
        return result

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            result.errors.append("slate is missing a header row")
            return result
        raw_rows = list(reader)

    if not raw_rows:
        result.errors.append("slate has no game rows")
        return result

    as_of_dt: datetime | None = None
    if as_of is not None:
        try:
            as_of_dt = parse_timestamp(as_of, "as_of", "command")
        except ValueError as exc:
            result.errors.append(str(exc))
            return result

    seen_orders: dict[str, int] = {}
    seen_game_ids: dict[str, int] = {}

    for index, raw in enumerate(raw_rows, start=2):
        display_order = (raw.get("display_order") or "").strip()
        label = _row_label(index, display_order or None)
        row_errors: list[str] = []

        if not display_order:
            row_errors.append(f"{label}: display_order is required")
        elif display_order in seen_orders:
            row_errors.append(
                f"{label}: duplicate display_order={display_order} "
                f"(also row {seen_orders[display_order]})"
            )
        else:
            seen_orders[display_order] = index

        game_id = (raw.get("cfbd_game_id") or "").strip()
        if not game_id:
            row_errors.append(f"{label}: cfbd_game_id is required and must be nonempty")
        elif game_id in seen_game_ids:
            row_errors.append(
                f"{label}: duplicate cfbd_game_id={game_id} "
                f"(also row {seen_game_ids[game_id]})"
            )
        else:
            seen_game_ids[game_id] = index

        away = (raw.get("away_team") or "").strip()
        home = (raw.get("home_team") or "").strip()
        if not away:
            row_errors.append(f"{label}: away_team is required")
        if not home:
            row_errors.append(f"{label}: home_team is required")
        if away and home and away == home:
            row_errors.append(
                f"{label}: away_team and home_team must not be the same team"
            )

        neutral_site: bool | None = None
        try:
            neutral_site = parse_boolean(
                raw.get("neutral_site", ""), "neutral_site", label
            )
        except ValueError as exc:
            row_errors.append(str(exc))

        lock_at: datetime | None = None
        captured_at: datetime | None = None
        try:
            lock_at = parse_timestamp(raw.get("lock_at_utc", ""), "lock_at_utc", label)
            if lock_at is None:
                row_errors.append(f"{label}: lock_at_utc is required")
        except ValueError as exc:
            row_errors.append(str(exc))
        try:
            captured_at = parse_timestamp(
                raw.get("captured_at_utc", ""), "captured_at_utc", label
            )
            if captured_at is None:
                row_errors.append(f"{label}: captured_at_utc is required")
        except ValueError as exc:
            row_errors.append(str(exc))

        if lock_at is not None and captured_at is not None and captured_at >= lock_at:
            row_errors.append(
                f"{label}: captured_at_utc must precede lock_at_utc "
                f"({captured_at.isoformat()} >= {lock_at.isoformat()})"
            )

        if as_of_dt is not None and lock_at is not None and as_of_dt > lock_at:
            row_errors.append(
                f"{label}: --as-of {as_of_dt.isoformat()} is after lock_at_utc "
                f"{lock_at.isoformat()}"
            )

        away_ml: float | None = None
        home_ml: float | None = None
        try:
            away_ml = parse_moneyline(
                raw.get("away_moneyline", ""), "away_moneyline", label
            )
        except ValueError as exc:
            row_errors.append(str(exc))
        try:
            home_ml = parse_moneyline(
                raw.get("home_moneyline", ""), "home_moneyline", label
            )
        except ValueError as exc:
            row_errors.append(str(exc))

        if away_ml is None or home_ml is None:
            result.warnings.append(
                f"{label}: missing moneyline; recommendation engine needs an explicit fallback"
            )

        espn_id = (raw.get("espn_game_id") or "").strip()
        if not espn_id:
            result.warnings.append(f"{label}: espn_game_id is missing")

        away_pub: float | None = None
        home_pub: float | None = None
        try:
            away_pub = parse_optional_float(raw.get("away_public_pick_pct", ""))
            home_pub = parse_optional_float(raw.get("home_public_pick_pct", ""))
        except ValueError:
            row_errors.append(f"{label}: public-pick percentages must be numeric")

        if away_pub is not None and not 0 <= away_pub <= 100:
            row_errors.append(
                f"{label}: away_public_pick_pct must be between 0 and 100"
            )
        if home_pub is not None and not 0 <= home_pub <= 100:
            row_errors.append(
                f"{label}: home_public_pick_pct must be between 0 and 100"
            )
        if (
            away_pub is not None
            and home_pub is not None
            and abs((away_pub + home_pub) - 100.0) > PUBLIC_PCT_TOLERANCE
        ):
            row_errors.append(
                f"{label}: away_public_pick_pct + home_public_pick_pct must equal 100 "
                f"(got {away_pub + home_pub})"
            )

        result.errors.extend(row_errors)
        if row_errors:
            continue

        result.rows.append(
            {
                "display_order": int(display_order),
                "season": (raw.get("season") or "").strip() or None,
                "contest_week": (raw.get("contest_week") or "").strip() or None,
                "cfbd_game_id": game_id,
                "espn_game_id": espn_id or None,
                "away_team": away,
                "home_team": home,
                "neutral_site": neutral_site,
                "away_moneyline": away_ml,
                "home_moneyline": home_ml,
                "away_public_pick_pct": away_pub,
                "home_public_pick_pct": home_pub,
                "lock_at_utc": lock_at.isoformat().replace("+00:00", "Z")
                if lock_at
                else None,
                "captured_at_utc": (
                    captured_at.isoformat().replace("+00:00", "Z")
                    if captured_at
                    else None
                ),
                "spread_home": parse_optional_float(raw.get("spread_home", ""))
                if "spread_home" in raw
                else None,
                "_source": raw,
            }
        )

    result.rows.sort(key=lambda row: (row["display_order"], row["cfbd_game_id"]))
    return result
