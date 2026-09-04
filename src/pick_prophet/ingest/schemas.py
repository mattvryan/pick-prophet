"""CFBD endpoint payload contracts. Fail loudly on schema drift."""

from __future__ import annotations

from typing import Any

# Required keys checked on the first row of each array payload.
ENDPOINT_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "games": ("id", "season", "week"),
    "lines": ("id",),
    "rankings": ("season", "week", "polls"),
    "fpi": ("team",),
    "sp": ("team",),
    "elo": ("team",),
}


def validate_endpoint_payload(name: str, payload: Any) -> None:
    """Raise TypeError/ValueError with an actionable message when malformed."""

    if not isinstance(payload, list):
        raise TypeError(
            f"CFBD {name}: expected a JSON array, got {type(payload).__name__}"
        )
    required = ENDPOINT_REQUIRED_FIELDS.get(name)
    if required is None:
        raise ValueError(f"CFBD {name}: unknown endpoint contract")
    if not payload:
        return
    row = payload[0]
    if not isinstance(row, dict):
        raise TypeError(
            f"CFBD {name}: expected object rows, got {type(row).__name__}"
        )
    missing = [key for key in required if key not in row]
    if missing:
        raise ValueError(
            f"CFBD {name}: schema drift; missing required fields {missing} "
            f"on first row keys={sorted(row)}"
        )
