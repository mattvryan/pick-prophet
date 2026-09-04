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
    week_coverage: list[dict[str, Any]] = field(default_factory=list)
    missingness: dict[str, Any] = field(default_factory=dict)
    usable_for: dict[str, str] = field(default_factory=dict)

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

    # Week-level coverage (no silent row drops — every week present is reported).
    weeks = sorted(
        {
            w
            for w in (_to_int(r.get("week")) for r in rows)
            if w is not None
        }
    )
    week_coverage: list[dict[str, Any]] = []
    for week in weeks:
        week_rows = [r for r in rows if _to_int(r.get("week")) == week]
        week_coverage.append(
            {
                "season": audit.season,
                "week": week,
                "rows": len(week_rows),
                "completed": sum(
                    1
                    for r in week_rows
                    if _to_float(r.get("home_points")) is not None
                    and _to_float(r.get("away_points")) is not None
                ),
                "with_odds": sum(
                    1
                    for r in week_rows
                    if _to_float(r.get("spread_home")) is not None
                    or _to_float(r.get("home_implied_prob")) is not None
                ),
                "with_elo": sum(
                    1
                    for r in week_rows
                    if _to_float(r.get("elo_home")) is not None
                    or _to_float(r.get("elo_away")) is not None
                ),
                "with_ap_rank": sum(
                    1
                    for r in week_rows
                    if _to_int(r.get("ap_home_rank")) is not None
                    or _to_int(r.get("ap_away_rank")) is not None
                ),
            }
        )
    audit.week_coverage = week_coverage

    if weeks:
        expected = list(range(min(weeks), max(weeks) + 1))
        missing_weeks = [w for w in expected if w not in weeks]
        if missing_weeks:
            audit.add(
                CheckResult(
                    "week_continuity",
                    "warn",
                    f"missing week numbers inside span: {missing_weeks}",
                    missing_weeks,
                )
            )
        else:
            audit.add(
                CheckResult(
                    "week_continuity",
                    "pass",
                    f"weeks {min(weeks)}–{max(weeks)} present with no interior gaps",
                    {"min": min(weeks), "max": max(weeks)},
                )
            )
    else:
        audit.add(
            CheckResult("week_continuity", "fail", "no parseable week values", None)
        )

    # Structural vs join/adapter missingness for ratings and ranks.
    def _present(column: str) -> int:
        return sum(1 for r in rows if not _is_blank(r.get(column)))

    fpi_present = _present("fpi_home") + _present("fpi_away")
    sp_present = _present("sp_home") + _present("sp_away")
    ap_present = _present("ap_home_rank") + _present("ap_away_rank")
    coaches_present = _present("coaches_home_rank") + _present("coaches_away_rank")
    cfp_present = _present("cfp_home_rank") + _present("cfp_away_rank")
    provider_col_present = "line_provider_count" in (rows[0] if rows else {})
    providers = sum(
        1 for r in rows if (_to_int(r.get("line_provider_count")) or 0) > 0
    )
    provider_frac = providers / len(rows) if rows else 0.0
    if not provider_col_present:
        audit.add(
            CheckResult(
                "line_provider_coverage",
                "warn",
                "line_provider_count column absent",
                {"class": "column_absent"},
            )
        )
    else:
        provider_status = (
            "pass"
            if provider_frac >= 0.9
            else ("warn" if provider_frac >= 0.5 else "fail")
        )
        audit.add(
            CheckResult(
                "line_provider_coverage",
                provider_status,
                f"{providers}/{len(rows)} rows have line_provider_count > 0 ({provider_frac:.1%})",
                {"rows_with_providers": providers, "fraction": provider_frac},
            )
        )

    if fpi_present == 0 and "fpi_home" in (rows[0] if rows else {}):
        fpi_class = "structural_unjoined"
        fpi_detail = (
            "FPI columns are entirely null (season-level CFBD pulls deliberately "
            "unjoined until dated weekly archives exist)"
        )
        fpi_status = "pass"
    elif fpi_present == 0:
        fpi_class = "column_absent"
        fpi_detail = "FPI columns absent from CSV"
        fpi_status = "warn"
    elif fpi_present < len(rows) * 0.05:
        fpi_class = "join_or_adapter_failure"
        fpi_detail = f"FPI nearly empty ({fpi_present} non-null cells); treat as join failure"
        fpi_status = "warn"
    else:
        fpi_class = "partial_coverage"
        fpi_detail = f"FPI non-null cells={fpi_present}"
        fpi_status = "warn"

    if sp_present == 0 and "sp_home" in (rows[0] if rows else {}):
        sp_class = "structural_unjoined"
        sp_detail = (
            "SP+ columns are entirely null (season-level CFBD pulls deliberately "
            "unjoined until dated weekly archives exist)"
        )
        sp_status = "pass"
    elif sp_present == 0:
        sp_class = "column_absent"
        sp_detail = "SP+ columns absent from CSV"
        sp_status = "warn"
    elif sp_present < len(rows) * 0.05:
        sp_class = "join_or_adapter_failure"
        sp_detail = f"SP+ nearly empty ({sp_present} non-null cells); treat as join failure"
        sp_status = "warn"
    else:
        sp_class = "partial_coverage"
        sp_detail = f"SP+ non-null cells={sp_present}"
        sp_status = "warn"

    audit.add(CheckResult("fpi_missingness", fpi_status, fpi_detail, {"class": fpi_class}))
    audit.add(CheckResult("sp_missingness", sp_status, sp_detail, {"class": sp_class}))

    # Ranks: sparse is structural (unranked teams / early CFP).
    ap_frac = ap_present / (2 * len(rows))
    audit.add(
        CheckResult(
            "rank_coverage",
            "pass",
            (
                f"AP non-null cells={ap_present}, coaches={coaches_present}, "
                f"CFP={cfp_present} (sparse ranks are structural for unranked teams)"
            ),
            {
                "ap_non_null": ap_present,
                "coaches_non_null": coaches_present,
                "cfp_non_null": cfp_present,
                "class": "structural_sparse",
                "ap_fraction_of_cells": ap_frac,
            },
        )
    )

    audit.missingness = {
        "fpi": {"class": fpi_class, "non_null_cells": fpi_present},
        "sp": {"class": sp_class, "non_null_cells": sp_present},
        "ap_rank": {"class": "structural_sparse", "non_null_cells": ap_present},
        "coaches_rank": {"class": "structural_sparse", "non_null_cells": coaches_present},
        "cfp_rank": {"class": "structural_sparse", "non_null_cells": cfp_present},
        "elo": {
            "class": "partial_coverage" if elo_frac < 1.0 else "complete",
            "fraction": elo_frac,
        },
        "odds": {
            "class": "partial_coverage" if odds_frac < 1.0 else "complete",
            "fraction": odds_frac,
        },
    }

    # Per-source usability for later builds (never silently drop the season).
    def _usable(gate: str) -> str:
        if audit.status == "fail":
            return "blocked_integrity"
        return gate

    audit.usable_for = {
        "market_baseline": _usable(
            "yes" if odds_frac >= 0.9 and audit.status != "fail" else "thin_coverage"
        ),
        "elo_models": _usable(
            "yes" if elo_frac >= 0.7 and audit.status != "fail" else "thin_coverage"
        ),
        "fpi_models": "blocked_structural"
        if fpi_class == "structural_unjoined"
        else ("blocked_join" if fpi_class == "join_or_adapter_failure" else "review"),
        "sp_models": "blocked_structural"
        if sp_class == "structural_unjoined"
        else ("blocked_join" if sp_class == "join_or_adapter_failure" else "review"),
        "rank_features": _usable("yes_with_missing_indicators"),
        "protocol_1_0_0_fold": _usable(
            "yes"
            if audit.season in range(2017, 2026) and audit.status != "fail"
            else "out_of_window"
        ),
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
        "week_coverage": audit.week_coverage,
        "missingness": audit.missingness,
        "usable_for": audit.usable_for,
        "checks": [asdict(c) for c in audit.checks],
        # Preserve thin summary fields used by older tooling.
        "completed_games": audit.counts.get("completed_games"),
        "known_pickem_games": audit.counts.get("known_pickem_games"),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output


def recommend_evaluation_windows(audits: list[SeasonAudit]) -> dict[str, Any]:
    """Recommend usable seasons per source without silently dropping any season."""

    seasons = sorted(a.season for a in audits if a.season > 0)
    by_season = {a.season: a for a in audits if a.season > 0}

    def seasons_where(predicate) -> list[int]:
        return [s for s in seasons if predicate(by_season[s])]

    return {
        "all_discovered_seasons": seasons,
        "never_silently_dropped": True,
        "market_baseline_seasons": seasons_where(
            lambda a: a.usable_for.get("market_baseline") == "yes"
        ),
        "elo_model_seasons": seasons_where(
            lambda a: a.usable_for.get("elo_models") == "yes"
        ),
        "fpi_model_seasons": seasons_where(
            lambda a: a.usable_for.get("fpi_models") == "yes"
        ),
        "sp_model_seasons": seasons_where(
            lambda a: a.usable_for.get("sp_models") == "yes"
        ),
        "protocol_1_0_0_research_window": seasons_where(
            lambda a: a.usable_for.get("protocol_1_0_0_fold") == "yes"
        ),
        "integrity_blocked_seasons": seasons_where(lambda a: a.status == "fail"),
        "warn_seasons": seasons_where(lambda a: a.status == "warn"),
        "notes": [
            "FPI/SP+ remain structurally blocked until dated weekly archives exist.",
            "Thin-coverage seasons stay in the window but should be labelled in reports.",
            "Protocol 1.0.0 test seasons remain 2018–2025 regardless of thin coverage.",
        ],
    }


def write_machine_readable(
    audits: list[SeasonAudit],
    *,
    summary_json: Path,
    week_csv: Path,
    windows_json: Path,
) -> dict[str, Path]:
    summary = {
        "audited_at": datetime.now(UTC).isoformat(),
        "seasons": [
            {
                "season": a.season,
                "path": a.path,
                "status": a.status,
                "rows": a.rows,
                "counts": a.counts,
                "missingness": a.missingness,
                "usable_for": a.usable_for,
                "checks": [asdict(c) for c in a.checks],
            }
            for a in sorted(audits, key=lambda x: x.season)
        ],
        "evaluation_windows": recommend_evaluation_windows(audits),
    }
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    week_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "season",
        "week",
        "rows",
        "completed",
        "with_odds",
        "with_elo",
        "with_ap_rank",
    ]
    with week_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for audit in sorted(audits, key=lambda a: a.season):
            for row in audit.week_coverage:
                writer.writerow(row)

    windows = recommend_evaluation_windows(audits)
    windows_json.parent.mkdir(parents=True, exist_ok=True)
    windows_json.write_text(json.dumps(windows, indent=2, sort_keys=True) + "\n")
    return {
        "summary_json": summary_json,
        "week_csv": week_csv,
        "windows_json": windows_json,
    }


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
        "| Season | Rows | Status | Completed | Odds | Elo | Joint | Neutral T/F | Market | Elo models | FPI |",
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for audit in sorted(audits, key=lambda a: a.season):
        c = audit.counts
        u = audit.usable_for
        lines.append(
            "| {season} | {rows} | {status} | {completed} | {odds} | {elo} | {joint} | {nt}/{nf} | {market} | {elo_m} | {fpi} |".format(
                season=audit.season,
                rows=audit.rows,
                status=audit.status,
                completed=c.get("completed_games", ""),
                odds=c.get("rows_with_odds", ""),
                elo=c.get("rows_with_elo", ""),
                joint=c.get("rows_with_odds_and_elo", ""),
                nt=c.get("neutral_site_true", ""),
                nf=c.get("neutral_site_false", ""),
                market=u.get("market_baseline", ""),
                elo_m=u.get("elo_models", ""),
                fpi=u.get("fpi_models", ""),
            )
        )

    windows = recommend_evaluation_windows(audits)
    lines.extend(
        [
            "",
            "## Recommended evaluation windows",
            "",
            f"- Market baseline seasons: `{windows['market_baseline_seasons']}`",
            f"- Elo model seasons: `{windows['elo_model_seasons']}`",
            f"- FPI model seasons: `{windows['fpi_model_seasons']}` (expect empty until weekly archives)",
            f"- SP+ model seasons: `{windows['sp_model_seasons']}` (expect empty until weekly archives)",
            f"- Protocol 1.0.0 research seasons retained: `{windows['protocol_1_0_0_research_window']}`",
            f"- Integrity-blocked seasons: `{windows['integrity_blocked_seasons']}`",
            "",
        ]
    )
    for note in windows["notes"]:
        lines.append(f"- {note}")

    lines.extend(["", "## Per-season checks", ""])
    for audit in sorted(audits, key=lambda a: a.season):
        lines.append(f"### {audit.season} (`{audit.path}`)")
        lines.append("")
        lines.append(f"Overall status: **{audit.status}**")
        lines.append("")
        lines.append(f"Usable for: `{audit.usable_for}`")
        lines.append("")
        if audit.week_coverage:
            lines.append(
                f"Weeks covered: {audit.week_coverage[0]['week']}–"
                f"{audit.week_coverage[-1]['week']} "
                f"({len(audit.week_coverage)} distinct)"
            )
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
            (
                "Fail means at least one season has a blocking integrity issue "
                "(duplicate IDs, broken outcomes, missing identities, or empty file)."
            ),
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
    summary_json: Path | None = None,
    week_csv: Path | None = None,
    windows_json: Path | None = None,
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

    if summary_json or week_csv or windows_json:
        write_machine_readable(
            audits,
            summary_json=summary_json
            or processed_root / "coverage_summary.json",
            week_csv=week_csv or processed_root / "coverage_by_week.csv",
            windows_json=windows_json
            or processed_root / "coverage_evaluation_windows.json",
        )
    return audits, markdown
