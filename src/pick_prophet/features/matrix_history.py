"""Chronological history and rest for the M07 modeling matrix."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class NonPositiveRestError(ValueError):
    """Raised when a prior kickoff is not strictly before the current kickoff."""


def _parse_kickoff(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _team_key(season: Any, team_id: Any, team_name: Any) -> tuple[Any, str, Any]:
    if team_id is not None and str(team_id).strip() != "":
        return (season, "id", int(team_id))
    return (season, "name", team_name)


def _win_pct(wins: int, losses: int) -> float | None:
    total = wins + losses
    if total <= 0:
        return None
    return wins / total


def _days_rest(current: datetime, prior: datetime) -> int:
    delta = (current - prior).total_seconds()
    if delta <= 0:
        raise NonPositiveRestError(
            f"non-positive rest interval: prior={prior.isoformat()} "
            f"current={current.isoformat()}"
        )
    return int(delta // 86400)


def attach_matrix_history(rows: list[dict[str, Any]]) -> None:
    """Recompute entering W-L, previous result, SOS, and days rest in place.

    Overwrites any pre-existing history fields. Uses only prior completed
    same-season games. Kickoff timestamps are the rest proxy.
    """

    ordered = sorted(
        rows,
        key=lambda r: (str(r.get("kickoff_utc") or ""), int(r["game_id"])),
    )
    record: dict[tuple[Any, str, Any], tuple[int, int]] = {}
    previous: dict[tuple[Any, str, Any], int | None] = {}
    opponents_faced: dict[tuple[Any, str, Any], list[tuple[Any, str, Any]]] = {}
    last_completed_kickoff: dict[tuple[Any, str, Any], datetime] = {}

    for row in ordered:
        season = row.get("season")
        home_key = _team_key(season, row.get("home_team_id"), row.get("home_team"))
        away_key = _team_key(season, row.get("away_team_id"), row.get("away_team"))
        kickoff = _parse_kickoff(row.get("kickoff_utc"))

        home_w, home_l = record.get(home_key, (0, 0))
        away_w, away_l = record.get(away_key, (0, 0))
        row["home_entering_wins"] = home_w
        row["home_entering_losses"] = home_l
        row["away_entering_wins"] = away_w
        row["away_entering_losses"] = away_l
        row["home_previous_result"] = previous.get(home_key)
        row["away_previous_result"] = previous.get(away_key)

        def sos_for(team_key: tuple[Any, str, Any]) -> float | None:
            faced = opponents_faced.get(team_key, [])
            values: list[float] = []
            for opp in faced:
                ow, ol = record.get(opp, (0, 0))
                pct = _win_pct(ow, ol)
                if pct is not None:
                    values.append(pct)
            if not values:
                return None
            return sum(values) / len(values)

        row["home_sos"] = sos_for(home_key)
        row["away_sos"] = sos_for(away_key)

        if kickoff is None:
            row["home_days_rest"] = None
            row["away_days_rest"] = None
        else:
            prior_home = last_completed_kickoff.get(home_key)
            prior_away = last_completed_kickoff.get(away_key)
            row["home_days_rest"] = (
                None if prior_home is None else _days_rest(kickoff, prior_home)
            )
            row["away_days_rest"] = (
                None if prior_away is None else _days_rest(kickoff, prior_away)
            )

        home_win = row.get("home_win")
        if home_win is None or home_win == "":
            continue
        if kickoff is not None:
            last_completed_kickoff[home_key] = kickoff
            last_completed_kickoff[away_key] = kickoff
        if int(home_win) == 1:
            record[home_key] = (home_w + 1, home_l)
            record[away_key] = (away_w, away_l + 1)
            previous[home_key] = 1
            previous[away_key] = 0
        else:
            record[home_key] = (home_w, home_l + 1)
            record[away_key] = (away_w + 1, away_l)
            previous[home_key] = 0
            previous[away_key] = 1
        opponents_faced.setdefault(home_key, []).append(away_key)
        opponents_faced.setdefault(away_key, []).append(home_key)
