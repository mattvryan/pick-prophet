"""Tests for versioned evaluation protocol folds and pairing."""

from __future__ import annotations

import pytest

from pick_prophet.evaluation.folds import (
    assert_train_precedes_test,
    expanding_folds,
    pair_game_ids,
)
from pick_prophet.evaluation.protocol import DEFAULT_PROTOCOL, load_protocol


def test_default_protocol_freeze() -> None:
    protocol = load_protocol("1.0.0")
    assert protocol.protocol_version == "1.0.0"
    assert protocol.test_seasons[0] == 2018
    assert protocol.test_seasons[-1] == 2025
    assert protocol.latest_oot_fold == 2025
    assert protocol.prospective_holdout == "2026_weekly_shadow"
    assert protocol.bootstrap_seed == 20260904


def test_unknown_protocol_fails() -> None:
    with pytest.raises(ValueError, match="unknown protocol"):
        load_protocol("9.9.9")


def test_expanding_folds_train_precedes_test() -> None:
    folds = expanding_folds(list(range(2017, 2026)), DEFAULT_PROTOCOL)
    assert [f.test_season for f in folds] == list(range(2018, 2026))
    assert folds[0].train_seasons == (2017,)
    assert folds[-1].train_seasons == tuple(range(2017, 2025))
    assert_train_precedes_test(folds)
    for fold in folds:
        assert max(fold.train_seasons) < fold.test_season


def test_future_season_does_not_change_earlier_fold_membership() -> None:
    base = expanding_folds([2017, 2018, 2019], DEFAULT_PROTOCOL)
    with_future = expanding_folds([2017, 2018, 2019, 2020], DEFAULT_PROTOCOL)
    earlier = {f.test_season: f.train_seasons for f in base}
    for fold in with_future:
        if fold.test_season in earlier:
            assert fold.train_seasons == earlier[fold.test_season]


def test_pair_game_ids_rejects_unequal_sets() -> None:
    assert pair_game_ids([3, 1, 2], [2, 3, 1]) == (1, 2, 3)
    with pytest.raises(ValueError, match="unequal game_id"):
        pair_game_ids([1, 2], [1, 3])
