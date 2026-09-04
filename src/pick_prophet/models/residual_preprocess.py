"""Fold-local preprocessing for M08 residual adjustment features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

UNKNOWN = "unknown"

CATEGORICAL_COLUMNS: frozenset[str] = frozenset(
    {
        "home_conference",
        "away_conference",
        "home_classification",
        "away_classification",
    }
)

# Declared Boolean predictors stored as canonical true/false in the matrix CSV.
BOOLEAN_COLUMNS: frozenset[str] = frozenset(
    {
        "home_field_advantage",
        "is_week_1",
        "is_weeks_1_3",
    }
)

# Opening / movement fields are structurally absent under CFBD historical timing.
STRUCTURALLY_MISSING_OPEN_MOVE: frozenset[str] = frozenset(
    {
        "spread_home_open",
        "total_open",
        "spread_move_home",
        "total_move",
    }
)


@dataclass
class FoldPreprocessor:
    columns: tuple[str, ...]
    feature_names_: list[str] = field(default_factory=list)
    numeric_medians_: dict[str, float] = field(default_factory=dict)
    numeric_means_: dict[str, float] = field(default_factory=dict)
    numeric_scales_: dict[str, float] = field(default_factory=dict)
    categorical_levels_: dict[str, list[str]] = field(default_factory=dict)
    categorical_reference_: dict[str, str | None] = field(default_factory=dict)
    # Source columns with no usable training values → no transformed columns.
    unavailable_source_columns_: list[str] = field(default_factory=list)
    _active_columns: tuple[str, ...] = ()
    _fitted: bool = False

    def fit(self, rows: list[dict[str, Any]]) -> FoldPreprocessor:
        self.feature_names_ = []
        self.numeric_medians_.clear()
        self.numeric_means_.clear()
        self.numeric_scales_.clear()
        self.categorical_levels_.clear()
        self.categorical_reference_.clear()
        self.unavailable_source_columns_ = []
        active: list[str] = []

        for col in self.columns:
            if col in CATEGORICAL_COLUMNS:
                raw_levels = {_normalize_cat(r.get(col)) for r in rows}
                non_unknown = sorted(level for level in raw_levels if level != UNKNOWN)
                if not non_unknown:
                    self.unavailable_source_columns_.append(col)
                    continue
                reference = non_unknown[0]
                emit = [level for level in non_unknown if level != reference]
                emit.append(UNKNOWN)
                self.categorical_levels_[col] = emit
                self.categorical_reference_[col] = reference
                active.append(col)
                for level in emit:
                    self.feature_names_.append(f"{col}={level}")
            else:
                values = [_as_float(r.get(col), boolean=col in BOOLEAN_COLUMNS) for r in rows]
                present = [v for v in values if v is not None]
                if not present:
                    # Do not emit a constant all-missing indicator block.
                    self.unavailable_source_columns_.append(col)
                    continue
                median = float(np.median(present))
                filled = [median if v is None else v for v in values]
                mean = float(np.mean(filled))
                std = float(np.std(filled, ddof=0))
                scale = std if std > 0 else 1.0
                self.numeric_medians_[col] = median
                self.numeric_means_[col] = mean
                self.numeric_scales_[col] = scale
                active.append(col)
                self.feature_names_.append(col)
                self.feature_names_.append(f"{col}__missing")

        self._active_columns = tuple(active)
        if len(self.feature_names_) != len(set(self.feature_names_)):
            raise ValueError("duplicate transformed feature names")
        self._fitted = True
        return self

    def transform(self, rows: list[dict[str, Any]]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("preprocessor not fitted")
        out = np.zeros((len(rows), len(self.feature_names_)), dtype=float)
        for i, row in enumerate(rows):
            j = 0
            for col in self._active_columns:
                if col in CATEGORICAL_COLUMNS:
                    level = _normalize_cat(row.get(col))
                    ref = self.categorical_reference_[col]
                    emit = self.categorical_levels_[col]
                    if ref is not None and level == ref:
                        assigned = None
                    elif level in emit:
                        assigned = level
                    elif emit:
                        assigned = UNKNOWN
                    else:
                        assigned = None
                    for emitted in emit:
                        out[i, j] = 1.0 if assigned == emitted else 0.0
                        j += 1
                else:
                    raw = _as_float(row.get(col), boolean=col in BOOLEAN_COLUMNS)
                    missing = 1.0 if raw is None else 0.0
                    value = self.numeric_medians_[col] if raw is None else float(raw)
                    scaled = (value - self.numeric_means_[col]) / self.numeric_scales_[
                        col
                    ]
                    out[i, j] = scaled
                    out[i, j + 1] = missing
                    j += 2
        return out

    def state_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "active_columns": list(self._active_columns),
            "unavailable_source_columns": list(self.unavailable_source_columns_),
            "feature_names": list(self.feature_names_),
            "numeric_medians": dict(self.numeric_medians_),
            "numeric_means": dict(self.numeric_means_),
            "numeric_scales": dict(self.numeric_scales_),
            "categorical_levels": {k: list(v) for k, v in self.categorical_levels_.items()},
            "categorical_reference": dict(self.categorical_reference_),
        }


def _normalize_cat(value: Any) -> str:
    if value is None or value == "":
        return UNKNOWN
    return str(value).strip()


def _as_float(value: Any, *, boolean: bool = False) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if boolean or isinstance(value, str):
        text = str(value).strip().lower()
        if text in {"true", "t", "yes", "y", "1"}:
            return 1.0
        if text in {"false", "f", "no", "n", "0"}:
            return 0.0
        if boolean:
            # Declared Boolean with non-canonical text → missing (do not float()).
            try:
                # Allow numeric 0/1 strings already handled; other numerics invalid.
                as_num = float(text)
            except (TypeError, ValueError):
                return None
            if as_num in (0.0, 1.0):
                return as_num
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def matrix_column_all_missing(rows: list[dict[str, Any]], column: str) -> bool:
    """True when every row lacks a usable value for ``column``."""

    boolean = column in BOOLEAN_COLUMNS
    if column in CATEGORICAL_COLUMNS:
        return all(_normalize_cat(r.get(column)) == UNKNOWN for r in rows)
    return all(_as_float(r.get(column), boolean=boolean) is None for r in rows)
