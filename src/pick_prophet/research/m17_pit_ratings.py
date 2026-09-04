"""Fail-closed contract for point-in-time rating observations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an explicit UTC timestamp")
    return datetime.fromisoformat(value).astimezone(UTC)


def validate_rating_observation(row: dict[str, Any], *, kickoff_utc: str) -> None:
    required = {
        "source",
        "source_version",
        "team_id",
        "rating_name",
        "rating_value",
        "published_at_utc",
        "effective_at_utc",
        "retrieved_at_utc",
    }
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"rating observation missing fields: {missing}")
    published = _utc(row["published_at_utc"], "published_at_utc")
    effective = _utc(row["effective_at_utc"], "effective_at_utc")
    retrieved = _utc(row["retrieved_at_utc"], "retrieved_at_utc")
    kickoff = _utc(kickoff_utc, "kickoff_utc")
    if published >= kickoff:
        raise ValueError("rating was not published before kickoff")
    if effective > published:
        raise ValueError("rating effective time cannot follow publication time")
    if retrieved < published:
        raise ValueError("retrieval cannot precede publication")
    float(row["rating_value"])
