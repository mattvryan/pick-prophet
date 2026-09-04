"""Grade a frozen weekly card against final scores."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pick_prophet.evaluation.metrics import score_probabilities
from pick_prophet.weekly.validate import parse_timestamp

SCHEMA_VERSION = "weekly_grade.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"true", "1", "yes"}


def _pick_probability(pick: str, away: str, home: str, market_prob: str | None) -> float | None:
    if market_prob in (None, ""):
        return None
    probability = float(market_prob)
    if pick == home:
        return probability
    if pick == away:
        # final_picks stores the picked side's win probability already in Week 1.
        # If the value looks like a home-side probability from recommendations,
        # callers should pass the picked-side probability. We treat the provided
        # market_win_probability as P(pick wins).
        return probability
    return None


def grade_week(
    *,
    week_dir: Path | str,
    results_path: Path | str,
    submission_path: Path | str | None = None,
    recommendations_path: Path | str | None = None,
    tiebreaker_path: Path | str | None = None,
    shadow_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    graded_at: str | None = None,
) -> dict[str, Path]:
    """Compare submitted picks to final results and write immutable grade artifacts."""

    week_dir = Path(week_dir)
    results_path = Path(results_path)
    submission_path = Path(submission_path) if submission_path else week_dir / "submission.json"
    recommendations_path = (
        Path(recommendations_path)
        if recommendations_path
        else week_dir / "recommendations-current" / "recommendations.csv"
    )
    if not recommendations_path.exists():
        alt = week_dir / "recommendations" / "recommendations.csv"
        if alt.exists():
            recommendations_path = alt
    tiebreaker_path = (
        Path(tiebreaker_path) if tiebreaker_path else week_dir / "tiebreaker" / "tiebreaker.json"
    )
    output_dir = Path(output_dir) if output_dir else week_dir / "results" / "grade"
    if output_dir.exists() and (
        (output_dir / "results.json").exists() or (output_dir / "grade.md").exists()
    ):
        raise FileExistsError(f"refusing to overwrite existing grade outputs: {output_dir}")

    graded = graded_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if graded_at:
        parse_timestamp(graded_at, "graded_at", "command")

    if not submission_path.exists():
        raise FileNotFoundError(f"submission record not found: {submission_path}")
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    submitted_picks = submission.get("picks") or []
    if not submitted_picks:
        raise ValueError("submission.json contains no picks")

    results_rows = _load_csv(results_path)
    results_by_order = {int(row["display_order"]): row for row in results_rows}
    if any(str(row.get("completed", "true")).lower() in {"false", "0", "no"} for row in results_rows):
        raise ValueError("results.csv contains incomplete games")
    for row in results_rows:
        if not row.get("winner"):
            raise ValueError(
                f"results display_order={row.get('display_order')} missing winner"
            )

    baseline_by_order: dict[int, dict[str, str]] = {}
    if recommendations_path.exists():
        for row in _load_csv(recommendations_path):
            baseline_by_order[int(row["display_order"])] = row

    shadow_status = "not_provided"
    shadow_by_game: dict[str, dict[str, str]] = {}
    if shadow_dir is not None:
        from pick_prophet.weekly.shadow import load_shadow_pack

        shadow_path = Path(shadow_dir)
        shadow_manifest = load_shadow_pack(shadow_path)
        shadow_status = str(shadow_manifest.get("status") or "unknown")
        for row in _load_csv(shadow_path / "shadow_compare.csv"):
            gid = str(row.get("cfbd_game_id") or "")
            if not gid:
                raise ValueError("shadow_compare row missing cfbd_game_id")
            if gid in shadow_by_game:
                raise ValueError(f"duplicate shadow game_id: {gid}")
            shadow_by_game[gid] = row

    game_rows: list[dict[str, Any]] = []
    y_true: list[int] = []
    probs: list[float] = []
    correct = 0
    baseline_correct = 0
    baseline_games = 0
    override_games = 0
    override_correct = 0
    override_baseline_correct = 0
    shadow_games = 0
    shadow_correct = 0
    market_shadow_agree = 0
    submitted_shadow_agree = 0

    for pick in sorted(submitted_picks, key=lambda row: int(row["display_order"])):
        order = int(pick["display_order"])
        result = results_by_order.get(order)
        if result is None:
            raise ValueError(f"no result for display_order={order}")
        winner = result["winner"]
        submitted = pick["pick"]
        is_correct = submitted == winner
        correct += int(is_correct)
        override = _bool(pick.get("manual_override"))
        baseline = baseline_by_order.get(order, {})
        baseline_pick = (baseline.get("baseline_pick") or "").strip() or None
        baseline_ok = baseline_pick == winner if baseline_pick else None
        if baseline_pick:
            baseline_games += 1
            baseline_correct += int(bool(baseline_ok))
        if override:
            override_games += 1
            override_correct += int(is_correct)
            if baseline_ok is not None:
                override_baseline_correct += int(baseline_ok)

        market_prob = pick.get("market_win_probability")
        pick_prob = _pick_probability(
            submitted,
            pick["away_team"],
            pick["home_team"],
            None if market_prob is None else str(market_prob),
        )
        # Score P(pick wins): truth is 1 if pick won.
        if pick_prob is not None:
            y_true.append(1 if is_correct else 0)
            probs.append(pick_prob)

        gid = str(result.get("cfbd_game_id") or pick.get("cfbd_game_id") or "")
        shadow_row = shadow_by_game.get(gid) if gid else None
        shadow_pick = None
        shadow_ok = None
        if shadow_status == "ml_shadow" and shadow_row is not None:
            shadow_pick = (shadow_row.get("shadow_pick") or "").strip() or None
            if shadow_pick:
                shadow_games += 1
                shadow_ok = shadow_pick == winner
                shadow_correct += int(bool(shadow_ok))
                if baseline_pick and shadow_pick == baseline_pick:
                    market_shadow_agree += 1
                if shadow_pick == submitted:
                    submitted_shadow_agree += 1

        game_rows.append(
            {
                "display_order": order,
                "cfbd_game_id": result.get("cfbd_game_id"),
                "away_team": pick["away_team"],
                "home_team": pick["home_team"],
                "submitted_pick": submitted,
                "baseline_pick": baseline_pick,
                "shadow_pick": shadow_pick,
                "winner": winner,
                "away_points": int(result["away_points"]),
                "home_points": int(result["home_points"]),
                "total_points": int(result["total_points"]),
                "correct": is_correct,
                "baseline_correct": baseline_ok,
                "shadow_correct": shadow_ok,
                "manual_override": override,
                "market_win_probability": pick_prob,
            }
        )

    games = len(game_rows)
    probability_metrics = score_probabilities(y_true, probs) if y_true else None

    tiebreaker_payload = None
    if tiebreaker_path.exists():
        tb = json.loads(tiebreaker_path.read_text(encoding="utf-8"))
        tb_game_id = str(tb.get("cfbd_game_id", ""))
        actual = None
        for row in game_rows:
            if str(row.get("cfbd_game_id")) == tb_game_id:
                actual = row["total_points"]
                break
        # Fall back to matching teams if needed.
        if actual is None:
            for row in game_rows:
                if (
                    row["away_team"] == tb.get("away_team")
                    and row["home_team"] == tb.get("home_team")
                ):
                    actual = row["total_points"]
                    break
        submitted_total = int(submission.get("tiebreaker_total"))
        recommended = tb.get("recommended_integer_total")
        if actual is None:
            raise ValueError("could not locate tiebreaker game in results")
        tiebreaker_payload = {
            "cfbd_game_id": tb_game_id or None,
            "submitted_total": submitted_total,
            "recommended_total": recommended,
            "actual_total": actual,
            "absolute_error": abs(submitted_total - actual),
            "recommended_absolute_error": (
                abs(int(recommended) - actual) if recommended is not None else None
            ),
        }

    override_delta = None
    if override_games:
        # Positive means overrides outperformed the baseline on those same games.
        override_delta = override_correct - override_baseline_correct

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "week_dir": str(week_dir),
        "graded_at_utc": graded,
        "submission_path": str(submission_path),
        "submission_sha256": _sha256(submission_path),
        "results_path": str(results_path),
        "results_sha256": _sha256(results_path),
        "recommendations_path": str(recommendations_path)
        if recommendations_path.exists()
        else None,
        "shadow_dir": str(shadow_dir) if shadow_dir is not None else None,
        "shadow_status": shadow_status,
        "games": games,
        "correct": correct,
        "accuracy": correct / games if games else None,
        "baseline_games": baseline_games,
        "baseline_correct": baseline_correct,
        "baseline_accuracy": baseline_correct / baseline_games if baseline_games else None,
        "shadow_games": shadow_games,
        "shadow_correct": shadow_correct,
        "shadow_accuracy": shadow_correct / shadow_games if shadow_games else None,
        "market_shadow_agree": market_shadow_agree,
        "submitted_shadow_agree": submitted_shadow_agree,
        "override_games": override_games,
        "override_correct": override_correct,
        "override_accuracy": override_correct / override_games if override_games else None,
        "override_delta_vs_baseline": override_delta,
        "confidence_points": None,
        "contest_mode": "standard",
        "probability_metrics": probability_metrics,
        "tiebreaker": tiebreaker_payload,
        "games_detail": game_rows,
        "notes": (
            "Confidence points are omitted for standard contests. "
            "market_win_probability is scored as P(submitted pick wins). "
            "no_ml_shadow packs are not double-counted as shadow model performance."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "results.json"
    md_path = output_dir / "grade.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Weekly grade",
        "",
        f"- Graded at: `{graded}`",
        f"- Record: **{correct}/{games}** ({payload['accuracy']:.1%})"
        if payload["accuracy"] is not None
        else f"- Record: **{correct}/{games}**",
        f"- Market baseline: **{baseline_correct}/{baseline_games}**"
        if baseline_games
        else "- Market baseline: unavailable",
        f"- Shadow status: `{shadow_status}`",
        f"- Shadow model: **{shadow_correct}/{shadow_games}**"
        if shadow_games
        else "- Shadow model: not scored",
        f"- Manual overrides: **{override_correct}/{override_games}**"
        if override_games
        else "- Manual overrides: none",
    ]
    if override_delta is not None:
        lines.append(
            f"- Override delta vs baseline on overridden games: **{override_delta:+d}**"
        )
    if probability_metrics:
        lines.append(
            "- Pick-probability metrics: "
            f"log loss {probability_metrics['log_loss']:.4f}, "
            f"Brier {probability_metrics['brier']:.4f}"
        )
    if tiebreaker_payload:
        lines.extend(
            [
                "",
                "## Tiebreaker",
                "",
                f"- Submitted: **{tiebreaker_payload['submitted_total']}**",
                f"- Actual total: **{tiebreaker_payload['actual_total']}**",
                f"- Absolute error: **{tiebreaker_payload['absolute_error']}**",
            ]
        )
    lines.extend(["", "## Games", ""])
    for row in game_rows:
        mark = "correct" if row["correct"] else "wrong"
        lines.append(
            f"{row['display_order']}. {row['away_team']} at {row['home_team']}: "
            f"picked **{row['submitted_pick']}**, winner **{row['winner']}** ({mark})"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "output_dir": output_dir}
