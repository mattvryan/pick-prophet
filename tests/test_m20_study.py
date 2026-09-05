from __future__ import annotations

from pick_prophet.features.matrix_v2 import CANDIDATE_FAMILIES
from pick_prophet.models.m20_study import build_variants


def test_variants_are_predeclared_and_use_only_candidate_columns() -> None:
    variants = build_variants()
    assert variants["market_only"] == ()
    assert set(variants["combined"]) == {
        column for columns in CANDIDATE_FAMILIES.values() for column in columns
    }
    for family, columns in CANDIDATE_FAMILIES.items():
        assert variants[f"family__{family}"] == columns
        assert not set(variants[f"lof__without_{family}"]) & set(columns)
