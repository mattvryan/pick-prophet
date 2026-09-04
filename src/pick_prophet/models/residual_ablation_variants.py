"""Predeclared M10 ablation / leave-family-out variant registries."""

from __future__ import annotations

from pick_prophet.features.matrix_schema import MODEL_FEATURE_COLUMNS
from pick_prophet.models.residual_preprocess import STRUCTURALLY_MISSING_OPEN_MOVE
from pick_prophet.models.residual_variants import (
    COMBINED_COLUMNS,
    HISTORY_COLUMNS,
    MARKET_CONTEXT_COLUMNS,
    PROHIBITED_ADJUSTMENT_EXACT,
    SITE_TEMPORAL_COLUMNS,
)

MIN_ESPN_N = 50
ANOMALOUS_SEASONS: tuple[int, ...] = (2020,)

# Opening/movement fields are unavailable under CFBD historical timing and are
# excluded from family evidence and M11 eligibility.
UNAVAILABLE_FOR_EVIDENCE: frozenset[str] = STRUCTURALLY_MISSING_OPEN_MOVE

FAMILIES: dict[str, tuple[str, ...]] = {
    "site_temporal": SITE_TEMPORAL_COLUMNS,
    "history": HISTORY_COLUMNS,
    "market_context": tuple(
        c for c in MARKET_CONTEXT_COLUMNS if c not in UNAVAILABLE_FOR_EVIDENCE
    ),
}

# Full family tuples before unavailable filtering (for documentation only).
FAMILIES_DECLARED: dict[str, tuple[str, ...]] = {
    "site_temporal": SITE_TEMPORAL_COLUMNS,
    "history": HISTORY_COLUMNS,
    "market_context": MARKET_CONTEXT_COLUMNS,
}


def eligible_single_features() -> tuple[str, ...]:
    """Ordered union of M08 families minus structurally unavailable columns."""

    ordered = tuple(
        dict.fromkeys((*SITE_TEMPORAL_COLUMNS, *HISTORY_COLUMNS, *MARKET_CONTEXT_COLUMNS))
    )
    return tuple(c for c in ordered if c not in UNAVAILABLE_FOR_EVIDENCE)


def combined_columns_for_evidence() -> tuple[str, ...]:
    return tuple(c for c in COMBINED_COLUMNS if c not in UNAVAILABLE_FOR_EVIDENCE)


def build_ablation_variants() -> dict[str, tuple[str, ...]]:
    variants: dict[str, tuple[str, ...]] = {"market_only": ()}
    for col in eligible_single_features():
        variants[f"single__{col}"] = (col,)
    for name, columns in FAMILIES.items():
        variants[f"family__{name}"] = columns
    combined = combined_columns_for_evidence()
    variants["combined"] = combined
    for name, columns in FAMILIES.items():
        drop = set(columns)
        variants[f"lof__without_{name}"] = tuple(c for c in combined if c not in drop)
    return variants


def assert_ablation_variants_valid(
    variants: dict[str, tuple[str, ...]] | None = None,
) -> None:
    variants = variants or build_ablation_variants()
    allowed = set(MODEL_FEATURE_COLUMNS)
    singles = set(eligible_single_features())
    combined = combined_columns_for_evidence()
    if "market_only" not in variants or variants["market_only"] != ():
        raise ValueError("market_only must map to empty columns")
    if "combined" not in variants or variants["combined"] != combined:
        raise ValueError("combined must equal evidence combined columns")
    for name, columns in variants.items():
        for col in columns:
            if col in UNAVAILABLE_FOR_EVIDENCE:
                raise ValueError(
                    f"{name}: structurally unavailable column {col!r} must not "
                    "appear in ablation evidence variants"
                )
            if col not in allowed:
                raise ValueError(f"{name}: {col!r} not in MODEL_FEATURE_COLUMNS")
            if col in PROHIBITED_ADJUSTMENT_EXACT:
                raise ValueError(f"{name}: prohibited column {col!r}")
            if col.startswith(("elo_", "fpi_")) or (
                col.startswith("sp_") and not col.startswith("spread_")
            ):
                raise ValueError(f"{name}: deferred rating column {col!r}")
        if name.startswith("single__"):
            col = name.removeprefix("single__")
            if columns != (col,):
                raise ValueError(f"{name}: must contain only source column {col!r}")
            if col not in singles:
                raise ValueError(f"{name}: {col!r} not in eligible single features")
        if name.startswith("family__"):
            fam = name.removeprefix("family__")
            if fam not in FAMILIES or columns != FAMILIES[fam]:
                raise ValueError(f"{name}: must match family {fam}")
        if name.startswith("lof__without_"):
            fam = name.removeprefix("lof__without_")
            expected = tuple(c for c in combined if c not in set(FAMILIES[fam]))
            if columns != expected:
                raise ValueError(f"{name}: incorrect leave-family-out columns")
