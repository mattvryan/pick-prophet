"""Audit processed season CSVs and emit a cross-season coverage report."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    name: str
    status: str  # pass | warn | fail
    detail: str
    value: Any = None


@dataclass
class SeasonAudit:
    season: int
    path: str
    rows: int
    status: str
    checks: list[CheckResult] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)
        if check.status == "fail":
            self.status = "fail"
        elif check.status == "warn" and self.status != "fail":
            self.status = "warn"


def _parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _to_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if _is_blank(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def audit_rows(rows: list[dict[str, Any]], *, season: int | None = None) -> SeasonAudit:
    if not rows:
        audit = SeasonAudit(
            season=season or 0,
            path="",
            rows=0,
            status="fail",
        )
        audit.add(CheckResult("non_empty", "fail", "CSV has zero data rows"))
        return audit

    inferred_season = season
    if inferred_season is None:
        seasons = {_to_int(r.get("season")) for r in rows}
        seasons.discard(None)
        inferred_season = next(iter(seasons)) if len(seasons) == 1 else 0

    audit = SeasonAudit(
        season=int(inferred_season or 0),
        path="",
        rows=len(rows),
        status="pass",
    )

    game_ids = [_to_int(r.get("game_id")) for r in rows]
    missing_ids = sum(g is None for g in game_ids)
    present_ids = [g for g in game_ids if g is not None]
    dupes = len(present_ids) - len(set(present_ids))
    if missing_ids or dupes:
        audit.add(
            CheckResult(
                "unique_game_id",
                "fail",
                f"missing_ids={missing_ids} duplicate_ids={dupes}",
                {"missing_ids": missing_ids, "duplicate_ids": dupes},
            )
        )
    else:
        audit.add(
            CheckResult(
                "unique_game_id",
                "pass",
                f"{len(present_ids)} unique game_id values",
                len(present_ids),
            )
        )

    outcome_bad = 0
    completed = 0
    for row in rows:
        hp = _to_float(row.get("home_points"))
        ap = _to_float(row.get("away_points"))
        hw = row.get("home_win")
        if hp is None or ap is None:
            if not _is_blank(hw):
                outcome_bad += 1
            continue
        completed += 1
        if hp == ap:
            if not _is_blank(hw):
                outcome_bad += 1
            continue
        expected = 1 if hp > ap else 0
        actual = _to_int(hw)
        if actual is None or actual != expected:
            outcome_bad += 1
    if outcome_bad:
        audit.add(
            CheckResult(
                "outcome_consistency",
                "fail",
                f"{outcome_bad} rows have inconsistent home_win vs points",
                outcome_bad,
            )
        )
    else:
        audit.add(
            CheckResult(
                "outcome_consistency",
                "pass",
                f"{completed} completed games with consistent outcomes",
                completed,
            )
        )

    incomplete = len(rows) - completed
    if incomplete and completed == 0:
        audit.add(
            CheckResult(
                "completed_outcomes",
                "fail",
                "no completed outcomes in season file",
                incomplete,
            )
        )
    elif incomplete:
        audit.add(
            CheckResult(
                "completed_outcomes",
                "warn",
                f"{incomplete} rows missing final scores",
                incomplete,
            )
        )
    else:
        audit.add(
            CheckResult(
                "completed_outcomes",
                "pass",
                "all rows have final scores",
                completed,
            )
        )

    has_odds = sum(
        1
        for r in rows
        if _to_float(r.get("spread_home")) is not None
        or _to_float(r.get("home_implied_prob")) is not None
    )
    has_elo = sum(
        1
        for r in rows
        if _to_float(r.get("elo_home")) is not None
        or _to_float(r.get("elo_away")) is not None
    )
    joint = sum(
        1
        for r in rows
        if (
            _to_float(r.get("spread_home")) is not None
            or _to_float(r.get("home_implied_prob")) is not None
        )
        and (
            _to_float(r.get("elo_home")) is not None
            or _to_float(r.get("elo_away")) is not None
        )
    )
    odds_frac = has_odds / len(rows)
    elo_frac = has_elo / len(rows)
    joint_frac = joint / len(rows)
    odds_status = "pass" if odds_frac >= 0.9 else ("warn" if odds_frac >= 0.5 else "fail")
    audit.add(
        CheckResult(
            "odds_coverage",
            odds_status,
            f"{has_odds}/{len(rows)} rows have spread or implied prob ({odds_frac:.1%})",
            {"rows_with_odds": has_odds, "fraction": odds_frac},
        )
    )
    elo_status = "pass" if elo_frac >= 0.7 else ("warn" if elo_frac >= 0.3 else "fail")
    audit.add(
        CheckResult(
            "elo_coverage",
            elo_status,
            f"{has_elo}/{len(rows)} rows have Elo ({elo_frac:.1%})",
            {"rows_with_elo": has_elo, "fraction": elo_frac},
        )
    )
    joint_status = (
        "pass" if joint_frac >= 0.7 else ("warn" if joint_frac >= 0.3 else "fail")
    )
    audit.add(
        CheckResult(
            "odds_rating_joint_coverage",
            joint_status,
            f"{joint}/{len(rows)} rows have both odds and Elo ({joint_frac:.1%})",
            {"rows_with_both": joint, "fraction": joint_frac},
        )
    )

    missing_identity = sum(
        1
        for r in rows
        if _is_blank(r.get("home_team"))
        or _is_blank(r.get("away_team"))
        or _is_blank(r.get("home_team_id"))
        or _is_blank(r.get("away_team_id"))
    )
    if missing_identity:
        audit.add(
            CheckResult(
                "team_identity",
                "fail",
                f"{missing_identity} rows missing team name or ID",
                missing_identity,
            )
        )
    else:
        audit.add(
            CheckResult(
                "team_identity",
                "pass",
                "all rows have home/away team names and IDs",
                0,
            )
        )

    neutral_true = 0
    neutral_false = 0
    neutral_missing = 0
    for r in rows:
        flag = _parse_bool(r.get("neutral_site"))
        if flag is True:
            neutral_true += 1
        elif flag is False:
            neutral_false += 1
        else:
            neutral_missing += 1
    if neutral_missing:
        audit.add(
            CheckResult(
                "neutral_site",
                "fail",
                f"{neutral_missing} rows with non-boolean neutral_site",
                {
                    "true": neutral_true,
                    "false": neutral_false,
                    "missing": neutral_missing,
                },
            )
        )
    else:
        audit.add(
            CheckResult(
                "neutral_site",
                "pass",
                f"neutral_site true={neutral_true} false={neutral_false}",
                {"true": neutral_true, "false": neutral_false, "missing": 0},
            )
        )

    audit.counts = {
        "rows": len(rows),
        "completed_games": completed,
        "incomplete_games": incomplete,
        "rows_with_odds": has_odds,
        "rows_with_elo": has_elo,
        "rows_with_odds_and_elo": joint,
        "neutral_site_true": neutral_true,
        "neutral_site_false": neutral_false,
        "neutral_site_missing": neutral_missing,
        "missing_team_identity": missing_identity,
    }
    return audit


def load_season_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def audit_season_file(path: Path) -> SeasonAudit:
    match = re.search(r"games_(\d{4})\.csv$", path.name)
    season = int(match.group(1)) if match else None
    rows = load_season_csv(path)
    audit = audit_rows(rows, season=season)
    audit.path = str(path)
    if season is not None:
        audit.season = season
    return audit


def discover_season_csvs(processed_root: Path) -> list[Path]:
    return sorted(processed_root.glob("games_????.csv"))


def write_season_quality(audit: SeasonAudit, output: Path | None = None) -> Path:
    path = Path(audit.path) if audit.path else None
    if output is None:
        if path is None:
            raise ValueError("output path required when audit.path is empty")
        output = path.with_suffix(".quality.json")
    payload = {
        "season": audit.season,
        "path": audit.path,
        "status": audit.status,
        "audited_at": datetime.now(UTC).isoformat(),
        "rows": audit.rows,
        "counts": audit.counts,
        "checks": [asdict(c) for c in audit.checks],
        # Preserve thin summary fields used by older tooling.
        "completed_games": audit.counts.get("completed_games"),
        "known_pickem_games": audit.counts.get("known_pickem_games"),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output


def render_coverage_report(audits: list[SeasonAudit]) -> str:
    lines = [
        "# Data coverage report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "Audits processed season CSVs under `data/processed/games_YYYY.csv`.",
        "Seasons are never silently dropped: every discovered file appears below.",
        "",
        "## Summary",
        "",
        "| Season | Rows | Status | Completed | Odds | Elo | Joint | Neutral T/F |",
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for audit in sorted(audits, key=lambda a: a.season):
        c = audit.counts
        lines.append(
            "| {season} | {rows} | {status} | {completed} | {odds} | {elo} | {joint} | {nt}/{nf} |".format(
                season=audit.season,
                rows=audit.rows,
                status=audit.status,
                completed=c.get("completed_games", ""),
                odds=c.get("rows_with_odds", ""),
                elo=c.get("rows_with_elo", ""),
                joint=c.get("rows_with_odds_and_elo", ""),
                nt=c.get("neutral_site_true", ""),
                nf=c.get("neutral_site_false", ""),
            )
        )
    lines.extend(["", "## Per-season checks", ""])
    for audit in sorted(audits, key=lambda a: a.season):
        lines.append(f"### {audit.season} (`{audit.path}`)")
        lines.append("")
        lines.append(f"Overall status: **{audit.status}**")
        lines.append("")
        for check in audit.checks:
            lines.append(f"- `{check.name}` **{check.status}**: {check.detail}")
        lines.append("")
    overall = "pass"
    if any(a.status == "fail" for a in audits):
        overall = "fail"
    elif any(a.status == "warn" for a in audits):
        overall = "warn"
    elif not audits:
        overall = "fail"
    lines.extend(
        [
            "## Gate",
            "",
            f"Cross-season gate: **{overall}**",
            "",
            "Fail means at least one season has a blocking integrity issue "
            "(duplicate IDs, broken outcomes, missing identities, or empty file).",
            "Warn means coverage is thin but the season remains in the window.",
            "",
        ]
    )
    return "\n".join(lines)


def run_coverage(
    processed_root: Path,
    *,
    report_path: Path,
    write_quality: bool = True,
) -> tuple[list[SeasonAudit], str]:
    paths = discover_season_csvs(processed_root)
    if not paths:
        audits: list[SeasonAudit] = []
        empty = SeasonAudit(season=0, path=str(processed_root), rows=0, status="fail")
        empty.add(
            CheckResult(
                "discover_seasons",
                "fail",
                f"no games_YYYY.csv files under {processed_root}",
            )
        )
        audits.append(empty)
    else:
        audits = [audit_season_file(path) for path in paths]
        if write_quality:
            for audit in audits:
                write_season_quality(audit)

    markdown = render_coverage_report(audits)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown)
    return audits, markdown
