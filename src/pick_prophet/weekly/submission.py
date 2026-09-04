"""Immutable confirmation records for ESPN Pick'em submissions."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pick_prophet.weekly.validate import parse_timestamp

SCHEMA_VERSION = "weekly_submission.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_bool(value: str, *, field: str, row_label: str) -> bool:
    text = (value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"{row_label}: {field} must be boolean, got {value!r}")


def _load_picks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"final picks not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} has no pick rows")

    picks: list[dict[str, Any]] = []
    seen_orders: set[int] = set()
    for index, raw in enumerate(rows, start=2):
        label = f"{path.name} row {index}"
        try:
            display_order = int((raw.get("display_order") or "").strip())
        except ValueError as exc:
            raise ValueError(f"{label}: display_order must be an integer") from exc
        if display_order in seen_orders:
            raise ValueError(f"{label}: duplicate display_order={display_order}")
        seen_orders.add(display_order)

        away = (raw.get("away_team") or "").strip()
        home = (raw.get("home_team") or "").strip()
        pick = (raw.get("pick") or "").strip()
        if not away or not home:
            raise ValueError(f"{label}: away_team and home_team are required")
        if pick not in {away, home}:
            raise ValueError(
                f"{label}: pick {pick!r} must be one of the two teams "
                f"({away!r}, {home!r})"
            )
        override = _parse_bool(
            raw.get("manual_override", ""), field="manual_override", row_label=label
        )
        if override and not (raw.get("review_note") or "").strip():
            raise ValueError(f"{label}: manual_override=true requires review_note")

        picks.append(
            {
                "display_order": display_order,
                "away_team": away,
                "home_team": home,
                "pick": pick,
                "market_win_probability": (raw.get("market_win_probability") or "").strip()
                or None,
                "manual_override": override,
                "review_note": (raw.get("review_note") or "").strip() or None,
            }
        )
    picks.sort(key=lambda row: row["display_order"])
    return picks


def _compare_picks(
    submitted: list[dict[str, Any]], final: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    final_by_order = {row["display_order"]: row for row in final}
    mismatches: list[dict[str, Any]] = []
    if {row["display_order"] for row in submitted} != set(final_by_order):
        mismatches.append(
            {
                "display_order": None,
                "field": "display_order_set",
                "submitted": sorted(row["display_order"] for row in submitted),
                "final_picks": sorted(final_by_order),
            }
        )
    for row in submitted:
        expected = final_by_order.get(row["display_order"])
        if expected is None:
            continue
        for field in ("away_team", "home_team", "pick"):
            if row[field] != expected[field]:
                mismatches.append(
                    {
                        "display_order": row["display_order"],
                        "field": field,
                        "submitted": row[field],
                        "final_picks": expected[field],
                    }
                )
    return mismatches


def record_submission(
    *,
    week_dir: Path | str,
    submitted_at: str,
    tiebreaker_total: int,
    operator: str | None = None,
    final_picks: Path | str | None = None,
    submitted_picks: Path | str | None = None,
    confirmation_file: Path | str | None = None,
    confirmation_sha256: str | None = None,
    notes: str | None = None,
    output_path: Path | str | None = None,
    recorded_at: str | None = None,
) -> Path:
    """Write an immutable submission confirmation record for a weekly directory."""

    week_dir = Path(week_dir)
    final_picks_path = Path(final_picks) if final_picks else week_dir / "final_picks.csv"
    submitted_picks_path = (
        Path(submitted_picks) if submitted_picks else final_picks_path
    )
    output = Path(output_path) if output_path else week_dir / "submission.json"

    parse_timestamp(submitted_at, "submitted_at", "command")
    if not isinstance(tiebreaker_total, int) or isinstance(tiebreaker_total, bool):
        raise TypeError("tiebreaker_total must be an integer")
    if tiebreaker_total <= 0:
        raise ValueError("tiebreaker_total must be a positive integer")

    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing submission record: {output}"
        )

    final_rows = _load_picks(final_picks_path)
    submitted_rows = _load_picks(submitted_picks_path)
    mismatches = _compare_picks(submitted_rows, final_rows)

    confirmation_path: str | None = None
    confirmation_digest = confirmation_sha256
    if confirmation_file is not None:
        confirmation = Path(confirmation_file)
        if not confirmation.exists():
            raise FileNotFoundError(f"confirmation file not found: {confirmation}")
        digest = _sha256(confirmation)
        if confirmation_digest and confirmation_digest != digest:
            raise ValueError(
                "confirmation_sha256 does not match confirmation_file contents"
            )
        confirmation_digest = digest
        confirmation_path = str(confirmation)

    final_card = week_dir / "final_card.md"
    recorded = recorded_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if recorded_at:
        parse_timestamp(recorded_at, "recorded_at", "command")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "week_dir": str(week_dir),
        "submitted_at_utc": submitted_at,
        "recorded_at_utc": recorded,
        "operator": operator,
        "tiebreaker_total": tiebreaker_total,
        "final_picks_path": str(final_picks_path),
        "final_picks_sha256": _sha256(final_picks_path),
        "final_card_path": str(final_card) if final_card.exists() else None,
        "final_card_sha256": _sha256(final_card) if final_card.exists() else None,
        "submitted_picks_path": str(submitted_picks_path),
        "submitted_picks_sha256": _sha256(submitted_picks_path),
        "confirmation_path": confirmation_path,
        "confirmation_sha256": confirmation_digest,
        "matches_final_picks": not mismatches,
        "mismatches": mismatches,
        "picks": submitted_rows,
        "notes": notes,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
