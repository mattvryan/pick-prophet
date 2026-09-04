"""Build the M07 allowlisted modeling feature matrix."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pick_prophet.features.market import market_logit
from pick_prophet.features.matrix_history import attach_matrix_history
from pick_prophet.features.matrix_schema import (
    MATRIX_COLUMNS,
    MATRIX_SCHEMA_VERSION,
    MODEL_FEATURE_COLUMNS,
    assert_no_deferred_ratings,
    assert_roles_disjoint,
)

FALSEY = {"", "false", "0", "no", "n"}


@dataclass
class Exclusion:
    season: Any
    source_snapshot: Any
    game_id: Any
    reason_code: str
    detail: str


@dataclass
class MatrixBuildResult:
    rows: list[dict[str, Any]]
    exclusions: list[Exclusion]
    input_rows: int
    input_paths: list[Path] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_season_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _has_identity(team_id: Any, team_name: Any) -> bool:
    if team_id is not None and str(team_id).strip() != "":
        return True
    return team_name is not None and str(team_name).strip() != ""


def _parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in FALSEY:
        return False
    if text in {"true", "1", "yes", "y"}:
        return True
    return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def validate_and_partition(
    rows: list[dict[str, Any]],
    *,
    season: Any,
    snapshot: Any,
) -> tuple[list[dict[str, Any]], list[Exclusion]]:
    retained: list[dict[str, Any]] = []
    exclusions: list[Exclusion] = []
    seen_ids: dict[int, str] = {}

    for idx, raw in enumerate(rows):
        game_id_raw = raw.get("game_id")
        try:
            game_id = int(game_id_raw) if game_id_raw not in (None, "") else None
        except (TypeError, ValueError):
            game_id = None
            exclusions.append(
                Exclusion(
                    season=season,
                    source_snapshot=snapshot,
                    game_id=game_id_raw,
                    reason_code="invalid_game_id",
                    detail=f"row={idx}",
                )
            )
            continue
        if game_id is None:
            exclusions.append(
                Exclusion(
                    season=season,
                    source_snapshot=snapshot,
                    game_id=None,
                    reason_code="missing_game_id",
                    detail=f"row={idx}",
                )
            )
            continue
        if game_id in seen_ids:
            raise ValueError(
                f"duplicate game_id={game_id} in season={season} "
                f"(first={seen_ids[game_id]})"
            )
        seen_ids[game_id] = f"row={idx}"

        season_val = raw.get("season", season)
        try:
            season_int = int(season_val) if season_val not in (None, "") else None
        except (TypeError, ValueError):
            season_int = None
        if season_int is None:
            exclusions.append(
                Exclusion(
                    season=season,
                    source_snapshot=snapshot,
                    game_id=game_id,
                    reason_code="invalid_season",
                    detail="missing/invalid season",
                )
            )
            continue

        try:
            week = int(raw["week"]) if raw.get("week") not in (None, "") else None
        except (TypeError, ValueError, KeyError):
            week = None
        if week is None:
            exclusions.append(
                Exclusion(
                    season=season_int,
                    source_snapshot=snapshot,
                    game_id=game_id,
                    reason_code="invalid_week",
                    detail="missing/invalid week",
                )
            )
            continue

        kickoff = raw.get("kickoff_utc")
        if kickoff is None or str(kickoff).strip() == "":
            exclusions.append(
                Exclusion(
                    season=season_int,
                    source_snapshot=snapshot,
                    game_id=game_id,
                    reason_code="missing_kickoff",
                    detail="kickoff_utc required",
                )
            )
            continue

        if not _has_identity(raw.get("home_team_id"), raw.get("home_team")):
            exclusions.append(
                Exclusion(
                    season=season_int,
                    source_snapshot=snapshot,
                    game_id=game_id,
                    reason_code="missing_home_identity",
                    detail="need home_team_id or home_team",
                )
            )
            continue
        if not _has_identity(raw.get("away_team_id"), raw.get("away_team")):
            exclusions.append(
                Exclusion(
                    season=season_int,
                    source_snapshot=snapshot,
                    game_id=game_id,
                    reason_code="missing_away_identity",
                    detail="need away_team_id or away_team",
                )
            )
            continue

        row = dict(raw)
        row["game_id"] = game_id
        row["season"] = season_int
        row["week"] = week
        if not row.get("source_snapshot"):
            row["source_snapshot"] = snapshot
        retained.append(row)

    return retained, exclusions


def derive_indicators(row: dict[str, Any]) -> None:
    week = int(row["week"])
    row["is_week_1"] = week == 1
    row["is_weeks_1_3"] = 1 <= week <= 3
    neutral = _parse_bool(row.get("neutral_site"))
    if neutral is None:
        # Treat missing neutral as unknown advantage → null? Spec ties to false/true.
        # Prefer False when missing would invent HFA; keep null via None and
        # serialize empty. But home_field_advantage is 1 if neutral false else 0.
        # If neutral missing, leave both null-ish: set neutral_site None and HFA None.
        row["neutral_site"] = None
        row["home_field_advantage"] = None
    else:
        row["neutral_site"] = neutral
        row["home_field_advantage"] = 0 if neutral else 1


def _normalize_pickem_pct(value: Any) -> float | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    # Accept 0-1 fractions by scaling; values already in percentage points stay.
    # Ambiguous at 1.0 (1% vs 100%); treat exclusive (0,1) as fractions.
    if 0.0 < parsed < 1.0:
        return parsed * 100.0
    return parsed


def project_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in MATRIX_COLUMNS:
        if col in {
            "is_week_1",
            "is_weeks_1_3",
            "neutral_site",
            "is_pickem_game",
            "moneyline_fabricated_from_spread",
        }:
            val = row.get(col)
            if isinstance(val, bool) or val is None:
                out[col] = val
            else:
                out[col] = _parse_bool(val)
        elif col in {"espn_home_pick_pct", "espn_expert_home_pct"}:
            out[col] = _normalize_pickem_pct(row.get(col))
        elif col == "home_field_advantage":
            out[col] = row.get(col)
        elif col in {
            "home_implied_prob",
            "home_market_logit",
            "spread_home",
            "total",
            "home_moneyline",
            "away_moneyline",
            "spread_home_open",
            "total_open",
            "spread_move_home",
            "total_move",
            "home_sos",
            "away_sos",
        }:
            out[col] = _as_float(row.get(col))
        elif col in {
            "game_id",
            "season",
            "week",
            "home_team_id",
            "away_team_id",
            "line_provider_count",
            "post_kick_provider_quotes_rejected",
            "home_entering_wins",
            "home_entering_losses",
            "away_entering_wins",
            "away_entering_losses",
            "home_previous_result",
            "away_previous_result",
            "home_days_rest",
            "away_days_rest",
            "home_win",
            "home_field_advantage",
        }:
            out[col] = _as_int(row.get(col)) if col != "home_field_advantage" else row.get(col)
        else:
            val = row.get(col)
            out[col] = None if val == "" else val

    # Derive baseline logit from vig-free implied when processed rows omit it.
    # Never fabricate probability from spread.
    if out.get("home_market_logit") is None and out.get("home_implied_prob") is not None:
        out["home_market_logit"] = market_logit(out["home_implied_prob"])

    # defaults for pickem audit
    if out.get("sampling_frame") in (None, ""):
        out["sampling_frame"] = "all_fbs"
    return out


def _serialize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_matrix_csv(rows: list[dict[str, Any]], path: Path) -> None:
    assert_roles_disjoint()
    assert_no_deferred_ratings(MATRIX_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        rows,
        key=lambda r: (str(r.get("kickoff_utc") or ""), int(r["game_id"])),
    )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=MATRIX_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        for row in ordered:
            writer.writerow({col: _serialize_cell(row.get(col)) for col in MATRIX_COLUMNS})


def write_missingness(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(rows)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("column", "null_count", "null_rate", "n_rows"),
            lineterminator="\n",
        )
        writer.writeheader()
        for col in MATRIX_COLUMNS:
            nulls = sum(1 for r in rows if r.get(col) is None or r.get(col) == "")
            rate = (nulls / n) if n else None
            writer.writerow(
                {
                    "column": col,
                    "null_count": nulls,
                    "null_rate": "" if rate is None else rate,
                    "n_rows": n,
                }
            )


def write_exclusions(exclusions: list[Exclusion], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "season",
                "source_snapshot",
                "game_id",
                "reason_code",
                "detail",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for item in exclusions:
            writer.writerow(
                {
                    "season": _serialize_cell(item.season),
                    "source_snapshot": _serialize_cell(item.source_snapshot),
                    "game_id": _serialize_cell(item.game_id),
                    "reason_code": item.reason_code,
                    "detail": item.detail,
                }
            )


DEFAULT_RATINGS_INVENTORY = {
    "elo": {
        "status": "deferred",
        "ref": "docs/ratings_feasibility.md",
        "reason": "M06: no publication timestamp; adapter implementation deferred",
    },
    "fpi": {
        "status": "deferred",
        "ref": "docs/ratings_feasibility.md",
        "reason": "M06: CFBD season-level only; omit until weekly PIT archive",
    },
    "sp": {
        "status": "deferred",
        "ref": "docs/ratings_feasibility.md",
        "reason": "M06: CFBD season-level only; omit until weekly PIT archive",
    },
}


def build_matrix_from_rows(
    season_rows: list[tuple[Any, Any, list[dict[str, Any]]]],
) -> MatrixBuildResult:
    """season_rows: list of (season, snapshot, raw_rows)."""

    assert_roles_disjoint()
    all_retained: list[dict[str, Any]] = []
    all_exclusions: list[Exclusion] = []
    input_rows = 0
    for season, snapshot, rows in season_rows:
        input_rows += len(rows)
        retained, exclusions = validate_and_partition(
            rows, season=season, snapshot=snapshot
        )
        all_exclusions.extend(exclusions)
        attach_matrix_history(retained)
        for row in retained:
            derive_indicators(row)
            projected = project_row(row)
            assert_no_deferred_ratings(projected.keys())
            # Ensure only allowlisted keys
            all_retained.append({col: projected.get(col) for col in MATRIX_COLUMNS})

    all_retained.sort(
        key=lambda r: (str(r.get("kickoff_utc") or ""), int(r["game_id"]))
    )
    return MatrixBuildResult(
        rows=all_retained,
        exclusions=all_exclusions,
        input_rows=input_rows,
    )


def build_manifest(
    *,
    input_paths: list[Path],
    result: MatrixBuildResult,
    matrix_path: Path,
    missingness_path: Path,
    exclusions_path: Path,
) -> dict[str, Any]:
    return {
        "exclusions_sha256": sha256_file(exclusions_path),
        "input_files": [
            {"path": str(path), "sha256": sha256_file(path)} for path in input_paths
        ],
        "input_rows": result.input_rows,
        "excluded_rows": len(result.exclusions),
        "matrix_schema_version": MATRIX_SCHEMA_VERSION,
        "matrix_sha256": sha256_file(matrix_path),
        "missingness_sha256": sha256_file(missingness_path),
        "model_feature_columns": list(MODEL_FEATURE_COLUMNS),
        "ratings_inventory": DEFAULT_RATINGS_INVENTORY,
        "retained_rows": len(result.rows),
    }


def write_json_stable(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n",
        encoding="utf-8",
    )


def write_run_envelope(*, output_dir: Path, generated_at_utc: str) -> Path:
    path = output_dir / "matrix_run.json"
    write_json_stable(
        {
            "generated_at_utc": generated_at_utc,
            "matrix_schema_version": MATRIX_SCHEMA_VERSION,
        },
        path,
    )
    return path


def parse_seasons_arg(text: str) -> list[int]:
    """Parse '2017,2018' or '2017-2025' or mixed '2017-2019,2021'."""

    seasons: list[int] = []
    for part in text.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start, end = int(start_s), int(end_s)
            if end < start:
                raise ValueError(f"invalid season range: {token}")
            seasons.extend(range(start, end + 1))
        else:
            seasons.append(int(token))
    if not seasons:
        raise ValueError("no seasons provided")
    return seasons


def build_and_write(
    *,
    input_dir: Path | None = None,
    input_paths: list[Path] | None = None,
    seasons: list[int],
    output_dir: Path,
    generated_at_utc: str | None = None,
) -> MatrixBuildResult:
    from datetime import UTC, datetime

    if input_paths is None:
        if input_dir is None:
            raise ValueError("input_dir or input_paths required")
        input_paths = sorted(input_dir.glob("games_*.csv"))

    season_rows: list[tuple[Any, Any, list[dict[str, Any]]]] = []
    used_paths: list[Path] = []
    for season in seasons:
        matches = sorted(p for p in input_paths if p.name == f"games_{season}.csv")
        if not matches:
            raise FileNotFoundError(f"missing games_{season}.csv in inputs")
        path = matches[0]
        used_paths.append(path)
        rows = load_season_csv(path)
        snapshot = rows[0].get("source_snapshot") if rows else path.stem
        season_rows.append((season, snapshot, rows))

    result = build_matrix_from_rows(season_rows)
    if result.input_rows != len(result.rows) + len(result.exclusions):
        raise AssertionError("input_rows != retained + excluded")

    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = output_dir / "games_matrix_v1.csv"
    missingness_path = output_dir / "matrix_missingness.csv"
    exclusions_path = output_dir / "matrix_exclusions.csv"
    write_matrix_csv(result.rows, matrix_path)
    write_missingness(result.rows, missingness_path)
    write_exclusions(result.exclusions, exclusions_path)
    manifest = build_manifest(
        input_paths=used_paths,
        result=result,
        matrix_path=matrix_path,
        missingness_path=missingness_path,
        exclusions_path=exclusions_path,
    )
    write_json_stable(manifest, output_dir / "matrix_manifest.json")
    stamp = generated_at_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    write_run_envelope(output_dir=output_dir, generated_at_utc=stamp)
    result.input_paths = used_paths
    return result
