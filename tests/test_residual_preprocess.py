"""Tests for M08 fold preprocessor."""

from __future__ import annotations

import numpy as np

from pick_prophet.models.residual_preprocess import UNKNOWN, FoldPreprocessor


def test_unseen_categorical_maps_to_unknown() -> None:
    train = [
        {"home_conference": "A", "spread_home": 1.0},
        {"home_conference": "B", "spread_home": 2.0},
    ]
    test = [{"home_conference": "C", "spread_home": 1.5}]
    prep = FoldPreprocessor(("home_conference", "spread_home")).fit(train)
    x = prep.transform(test)
    # reference is A (lex first); emit B and unknown
    assert "home_conference=B" in prep.feature_names_
    assert f"home_conference={UNKNOWN}" in prep.feature_names_
    unk_idx = prep.feature_names_.index(f"home_conference={UNKNOWN}")
    assert x[0, unk_idx] == 1.0


def test_all_missing_numeric_stable_schema() -> None:
    train = [{"spread_home": None}, {"spread_home": ""}]
    prep = FoldPreprocessor(("spread_home",)).fit(train)
    assert prep.feature_names_ == ["spread_home", "spread_home__missing"]
    x = prep.transform([{"spread_home": None}])
    np.testing.assert_allclose(x[0], [0.0, 1.0])


def test_train_only_statistics() -> None:
    train = [{"spread_home": 0.0}, {"spread_home": 2.0}]
    prep = FoldPreprocessor(("spread_home",)).fit(train)
    # mean of filled train = 1.0; if test leaked, mean would shift
    assert prep.numeric_means_["spread_home"] == 1.0
    x = prep.transform([{"spread_home": 100.0}])
    assert x.shape == (1, 2)


def test_reference_level_is_all_zero_block() -> None:
    train = [
        {"home_conference": "A"},
        {"home_conference": "B"},
    ]
    prep = FoldPreprocessor(("home_conference",)).fit(train)
    x = prep.transform([{"home_conference": "A"}])
    # A is reference → zeros on B and unknown
    assert np.all(x[0] == 0.0)
