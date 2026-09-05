"""M20 feature matrix 2.0 roles and deterministic family joins."""

from __future__ import annotations

import csv
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from pick_prophet.research.m18_team_form import FEATURE_COLUMNS as TEAM_FORM_FEATURES
from pick_prophet.research.m19_coaching_context import (
    FEATURE_COLUMNS as COACHING_FEATURES,
)

MATRIX_SCHEMA_VERSION = "2.0.0"
CANDIDATE_FAMILIES = {
    "team_form_efficiency": TEAM_FORM_FEATURES,
    "coaching_context": COACHING_FEATURES,
}
M20_CANDIDATE_COLUMNS = tuple(
    column for columns in CANDIDATE_FAMILIES.values() for column in columns
)
M20_AUDIT_COLUMNS = (
    "prior_games_home",
    "prior_games_away",
    "coaching_context_known",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _index(rows: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        game_id = int(row["game_id"])
        if game_id in result:
            raise ValueError(f"duplicate {label} game_id: {game_id}")
        result[game_id] = row
    return result


def build_matrix_v2_rows(
    base_rows: list[dict[str, Any]],
    form_rows: list[dict[str, Any]],
    coaching_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    form = _index(form_rows, "form")
    coaching = _index(coaching_rows, "coaching")
    base_ids = [int(row["game_id"]) for row in base_rows]
    if len(base_ids) != len(set(base_ids)):
        raise ValueError("duplicate base game_id")
    if set(form) != set(base_ids) or set(coaching) != set(base_ids):
        raise ValueError("M20 family game IDs must exactly match the base matrix")
    output = []
    for row in base_rows:
        game_id = int(row["game_id"])
        if int(row["season"]) >= 2026:
            raise ValueError("2026 rows are locked out of matrix 2.0 research")
        f = form[game_id]
        c = coaching[game_id]
        if int(f["season"]) != int(row["season"]) or int(c["season"]) != int(
            row["season"]
        ):
            raise ValueError(f"season mismatch for game_id={game_id}")
        joined = dict(row)
        for column in TEAM_FORM_FEATURES:
            joined[column] = f.get(column)
        for column in COACHING_FEATURES:
            joined[column] = c.get(column)
        joined["prior_games_home"] = f.get("prior_games_home")
        joined["prior_games_away"] = f.get("prior_games_away")
        joined["coaching_context_known"] = int(
            all(c.get(column) not in (None, "") for column in COACHING_FEATURES)
        )
        output.append(joined)
    return output


def build_matrix_v2(base: Path, form: Path, coaching: Path, output: Path) -> Path:
    rows = build_matrix_v2_rows(_read(base), _read(form), _read(coaching))
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output


def main() -> None:
    parser = ArgumentParser(description="Build feature matrix schema 2.0.0")
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--form", type=Path, required=True)
    parser.add_argument("--coaching", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_matrix_v2(args.base, args.form, args.coaching, args.output)


if __name__ == "__main__":
    main()
