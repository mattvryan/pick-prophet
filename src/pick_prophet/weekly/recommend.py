"""Market-baseline weekly recommendations (standard contest, no confidence points)."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pick_prophet.features.market import remove_two_way_vig
from pick_prophet.weekly.validate import validate_slate

OUTPUT_SCHEMA_VERSION = "weekly_recommendations.v1"
FINALIZED_MARKER = "FINALIZED"

RECOMMENDATION_FIELDS = [
    "display_order",
    "cfbd_game_id",
    "away_team",
    "home_team",
    "neutral_site",
    "lock_at_utc",
    "away_moneyline",
    "home_moneyline",
    "away_market_probability",
    "home_market_probability",
    "away_public_pick_pct",
    "home_public_pick_pct",
    "baseline_pick",
    "baseline_pick_probability",
    "public_disagreement",
    "upset_candidate",
    "recommendation_status",
    "warning",
]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fmt_prob(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.10f}".rstrip("0").rstrip(".") if value != 0 else "0"


def _fmt_optional(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _default_output_dir(slate_path: Path, as_of: str) -> Path:
    stamp = as_of.strip().replace(":", "").replace("+", "_")
    return slate_path.parent / "output" / f"recommend-{stamp}"


def build_recommendation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure market-baseline recommendations in ESPN display order."""

    output: list[dict[str, Any]] = []
    for row in rows:
        warning_parts: list[str] = []
        away_ml = row.get("away_moneyline")
        home_ml = row.get("home_moneyline")
        home_prob = remove_two_way_vig(home_ml, away_ml)
        away_prob = (1.0 - home_prob) if home_prob is not None else None

        baseline_pick = None
        baseline_prob = None
        status = "ok"

        if home_prob is None:
            # Slate CSV does not currently document a consensus spread field for
            # fallback picks. Do not invent probabilities.
            spread = row.get("spread_home")
            if spread is not None:
                warning_parts.append(
                    "moneyline unavailable; spread present but calibrated "
                    "probability unavailable"
                )
                status = "insufficient_data"
            else:
                warning_parts.append("missing two-way moneyline")
                status = "insufficient_data"
        elif home_prob > 0.5:
            baseline_pick = row["home_team"]
            baseline_prob = home_prob
        elif away_prob is not None and away_prob > 0.5:
            baseline_pick = row["away_team"]
            baseline_prob = away_prob
        else:
            status = "insufficient_data"
            warning_parts.append("market probabilities are exactly even")

        public_disagreement = None
        if baseline_pick is not None and baseline_prob is not None:
            if (
                baseline_pick == row["home_team"]
                and row.get("home_public_pick_pct") is not None
            ):
                public_disagreement = baseline_prob - (
                    row["home_public_pick_pct"] / 100.0
                )
            elif (
                baseline_pick == row["away_team"]
                and row.get("away_public_pick_pct") is not None
            ):
                public_disagreement = baseline_prob - (
                    row["away_public_pick_pct"] / 100.0
                )

        output.append(
            {
                "display_order": row["display_order"],
                "cfbd_game_id": row["cfbd_game_id"],
                "away_team": row["away_team"],
                "home_team": row["home_team"],
                "neutral_site": row["neutral_site"],
                "lock_at_utc": row["lock_at_utc"],
                "away_moneyline": away_ml,
                "home_moneyline": home_ml,
                "away_market_probability": away_prob,
                "home_market_probability": home_prob,
                "away_public_pick_pct": row.get("away_public_pick_pct"),
                "home_public_pick_pct": row.get("home_public_pick_pct"),
                "baseline_pick": baseline_pick,
                "baseline_pick_probability": baseline_prob,
                "public_disagreement": public_disagreement,
                "upset_candidate": False,
                "recommendation_status": status,
                "warning": "; ".join(warning_parts),
            }
        )
    return output


def render_card(rows: list[dict[str, Any]], *, as_of: str) -> str:
    lines = [
        "# Market baseline card",
        "",
        "**Market baseline — not the final submitted card**",
        "",
        f"- as_of: `{as_of}`",
        "- contest mode: standard (no confidence points are used)",
        f"- games: {len(rows)}",
        "",
        "## Selections (ESPN display order)",
        "",
    ]
    warnings: list[str] = []
    for row in rows:
        order = row["display_order"]
        matchup = f"{row['away_team']} @ {row['home_team']}"
        if row["neutral_site"]:
            matchup = f"{row['away_team']} vs {row['home_team']} (neutral)"
        if row["recommendation_status"] == "ok" and row["baseline_pick"]:
            lines.append(
                f"{order}. **{row['baseline_pick']}** "
                f"({_fmt_prob(row['baseline_pick_probability'])}) — {matchup}"
            )
            away_pub = row.get("away_public_pick_pct")
            home_pub = row.get("home_public_pick_pct")
            if away_pub is not None and home_pub is not None:
                lines.append(
                    f"   - public picks: {row['away_team']} {away_pub}% / "
                    f"{row['home_team']} {home_pub}%"
                )
                if row.get("public_disagreement") is not None:
                    lines.append(
                        f"   - public disagreement: {_fmt_prob(row['public_disagreement'])}"
                    )
        else:
            lines.append(
                f"{order}. **NO PICK** — {matchup} ({row['recommendation_status']})"
            )
        if row.get("warning"):
            warnings.append(f"display_order={order}: {row['warning']}")
        lines.append("")

    lines.extend(["## Missing-data warnings", ""])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    lines.append("")
    lines.append(
        "Confidence rank/points are omitted: this is a standard pick'em league "
        "with no confidence points."
    )
    lines.append("")
    return "\n".join(lines)


def write_recommendations_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    probability_fields = {
        "away_market_probability",
        "home_market_probability",
        "baseline_pick_probability",
        "public_disagreement",
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECOMMENDATION_FIELDS)
        writer.writeheader()
        for row in rows:
            serialized = {}
            for key in RECOMMENDATION_FIELDS:
                value = row.get(key)
                if key in probability_fields:
                    serialized[key] = _fmt_prob(value)
                else:
                    serialized[key] = _fmt_optional(value)
            writer.writerow(serialized)


def recommend(
    slate_path: Path | str,
    *,
    as_of: str,
    output_dir: Path | str | None = None,
    generation_timestamp: str | None = None,
) -> dict[str, Path]:
    """Validate a slate and write deterministic market-baseline artifacts."""

    slate_path = Path(slate_path)
    output_dir = (
        Path(output_dir) if output_dir else _default_output_dir(slate_path, as_of)
    )

    if (output_dir / FINALIZED_MARKER).exists():
        raise FileExistsError(
            f"refusing to overwrite finalized output directory: {output_dir}"
        )

    result = validate_slate(slate_path, as_of=as_of)
    if not result.ok:
        joined = "\n".join(result.errors)
        raise ValueError(f"slate validation failed:\n{joined}")

    rows = build_recommendation_rows(result.rows)
    output_dir.mkdir(parents=True, exist_ok=True)

    recommendations_path = output_dir / "recommendations.csv"
    card_path = output_dir / "card.md"
    manifest_path = output_dir / "run_manifest.json"

    write_recommendations_csv(recommendations_path, rows)
    card_path.write_text(render_card(rows, as_of=as_of), encoding="utf-8")

    generated_at = generation_timestamp or datetime.now(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    capture_manifest = slate_path.parent / "capture_manifest.json"
    capture_ids: list[str] = []
    if capture_manifest.exists():
        try:
            payload = json.loads(capture_manifest.read_text(encoding="utf-8"))
            for source in payload.get("sources", []):
                digest = source.get("sha256")
                if digest:
                    capture_ids.append(digest)
        except json.JSONDecodeError:
            pass

    valid_count = sum(1 for row in rows if row["recommendation_status"] == "ok")
    warning_count = len(result.warnings) + sum(1 for row in rows if row.get("warning"))

    manifest = {
        "input_path": str(slate_path),
        "input_sha256": _sha256_file(slate_path),
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "command_arguments": {
            "slate": str(slate_path),
            "as_of": as_of,
            "output_dir": str(output_dir),
        },
        "as_of": as_of,
        "generation_timestamp": generated_at,
        "contest_mode": "standard",
        "row_count": len(rows),
        "valid_recommendation_count": valid_count,
        "warning_count": warning_count,
        "validation_warnings": result.warnings,
        "capture_source_sha256": capture_ids,
        "notes": (
            "recommendations.csv and card.md are deterministic for identical "
            "slate contents and --as-of. generation_timestamp is isolated here."
        ),
        "output_hashes": {
            "recommendations.csv": _sha256_file(recommendations_path),
            "card.md": _sha256_file(card_path),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "recommendations": recommendations_path,
        "card": card_path,
        "run_manifest": manifest_path,
        "output_dir": output_dir,
    }
