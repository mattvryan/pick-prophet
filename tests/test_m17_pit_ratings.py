from __future__ import annotations

import pytest

from pick_prophet.research.m17_pit_ratings import validate_rating_observation


def _row() -> dict[str, object]:
    return {
        "source": "archive",
        "source_version": "v1",
        "team_id": 1,
        "rating_name": "elo",
        "rating_value": 1500,
        "effective_at_utc": "2024-08-30T12:00:00Z",
        "published_at_utc": "2024-08-30T13:00:00Z",
        "retrieved_at_utc": "2024-08-30T14:00:00Z",
    }


def test_valid_pre_kickoff_observation() -> None:
    validate_rating_observation(_row(), kickoff_utc="2024-08-31T16:00:00Z")


def test_missing_publication_time_fails() -> None:
    row = _row()
    del row["published_at_utc"]
    with pytest.raises(ValueError, match="missing fields"):
        validate_rating_observation(row, kickoff_utc="2024-08-31T16:00:00Z")


def test_post_kickoff_publication_fails() -> None:
    row = _row()
    row["published_at_utc"] = "2024-09-01T13:00:00Z"
    row["retrieved_at_utc"] = "2024-09-01T14:00:00Z"
    with pytest.raises(ValueError, match="before kickoff"):
        validate_rating_observation(row, kickoff_utc="2024-08-31T16:00:00Z")


def test_retrieval_does_not_substitute_for_publication() -> None:
    row = _row()
    row["retrieved_at_utc"] = "2024-08-30T12:30:00Z"
    with pytest.raises(ValueError, match="retrieval cannot precede"):
        validate_rating_observation(row, kickoff_utc="2024-08-31T16:00:00Z")
