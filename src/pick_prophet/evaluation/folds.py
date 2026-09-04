"""Expanding-window fold construction and paired game-ID selection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .protocol import DEFAULT_PROTOCOL, ProtocolConfig


@dataclass(frozen=True)
class Fold:
    test_season: int
    train_seasons: tuple[int, ...]
    fold_id: str

    @property
    def train_max_season(self) -> int:
        return max(self.train_seasons) if self.train_seasons else -1


def expanding_folds(
    available_seasons: Sequence[int],
    protocol: ProtocolConfig = DEFAULT_PROTOCOL,
) -> list[Fold]:
    """Build expanding-window folds for seasons present in the dataset.

    Only protocol test seasons that appear in ``available_seasons`` and have at
    least one prior available season are emitted. Training seasons are every
    available season strictly less than the test season (not only protocol
    research years), which preserves prior analyze.py behaviour while keeping
    the default research window documented on the protocol object.
    """

    seasons = sorted({int(s) for s in available_seasons})
    folds: list[Fold] = []
    for test_season in protocol.test_seasons:
        if test_season not in seasons:
            continue
        train = tuple(s for s in seasons if s < test_season)
        if not train:
            continue
        if max(train) >= test_season:
            raise AssertionError("training seasons must precede test season")
        folds.append(
            Fold(
                test_season=test_season,
                train_seasons=train,
                fold_id=f"test_{test_season}",
            )
        )
    return folds


def assert_train_precedes_test(folds: Iterable[Fold]) -> None:
    for fold in folds:
        if any(season >= fold.test_season for season in fold.train_seasons):
            raise ValueError(
                f"fold {fold.fold_id}: training season must precede test season"
            )


def pair_game_ids(
    left_ids: Iterable[Any],
    right_ids: Iterable[Any],
    *,
    context: str = "paired comparison",
) -> tuple[int, ...]:
    """Require identical game_id sets for promotion metrics.

    Returns the sorted shared ID tuple. Raises ``ValueError`` when sets differ.
    """

    left = {int(x) for x in left_ids}
    right = {int(x) for x in right_ids}
    if left != right:
        only_left = sorted(left - right)
        only_right = sorted(right - left)
        raise ValueError(
            f"{context}: unequal game_id sets "
            f"(only_left={only_left[:10]} only_right={only_right[:10]})"
        )
    return tuple(sorted(left))
