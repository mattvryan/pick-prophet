"""Versioned evaluation protocol configuration (M01)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

PROTOCOL_VERSION = "1.0.0"
PROTOCOL_V2_VERSION = "2.0.0"
BOOTSTRAP_SEED = 20260904
DEFAULT_N_BOOT = 500
LATEST_OOT_FOLD = 2025
PROSPECTIVE_HOLDOUT = "2026_weekly_shadow"
RESEARCH_SEASONS = tuple(range(2017, 2026))
TEST_SEASONS = tuple(range(2018, 2026))


@dataclass(frozen=True)
class ProtocolConfig:
    """Frozen walk-forward evaluation contract.

    Changing seasons, pairing rules, or metric definitions requires a new
    ``protocol_version`` rather than silent edits to this object.
    """

    protocol_version: str = PROTOCOL_VERSION
    research_seasons: tuple[int, ...] = RESEARCH_SEASONS
    test_seasons: tuple[int, ...] = TEST_SEASONS
    latest_oot_fold: int = LATEST_OOT_FOLD
    prospective_holdout: str = PROSPECTIVE_HOLDOUT
    bootstrap_seed: int = BOOTSTRAP_SEED
    n_boot: int = DEFAULT_N_BOOT
    calibration_bins: int = 10
    nested_fitting_rule: str = (
        "Scaler, imputer, hyperparameters, and calibration fit only on "
        "season < test_season; nested selection stays inside the training window. "
        "Required before promotion; full nested search may be implemented later."
    )
    favorite_strength_bands: tuple[str, ...] = (
        "lt_3",
        "3_to_7",
        "gt_7",
        "missing_spread",
    )
    required_slices: tuple[str, ...] = (
        "week_1",
        "weeks_1_3",
        "weeks_4_plus",
        "neutral_site",
        "favorite_lt_3",
        "favorite_3_to_7",
        "favorite_gt_7",
        "missing_spread",
        "all_fbs",
        "verified_espn_pickem",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_PROTOCOL = ProtocolConfig()

PROTOCOL_V2 = ProtocolConfig(
    protocol_version=PROTOCOL_V2_VERSION,
    # Historical outcomes through 2025 are available for predeclared
    # walk-forward research. 2026 remains a prospective-only stream.
    research_seasons=tuple(range(2017, 2026)),
    test_seasons=tuple(range(2018, 2026)),
    latest_oot_fold=2025,
    prospective_holdout="2026_weekly_shadow_locked",
    bootstrap_seed=20260904,
    n_boot=2000,
)


def load_protocol(version: str | None = None) -> ProtocolConfig:
    """Return a known protocol config. Unknown versions fail loudly."""

    if version is None or version == PROTOCOL_VERSION or version == "1.0.0":
        return DEFAULT_PROTOCOL
    if version == PROTOCOL_V2_VERSION:
        return PROTOCOL_V2
    raise ValueError(
        f"unknown protocol version {version!r}; registered versions are "
        f"{PROTOCOL_VERSION!r} and {PROTOCOL_V2_VERSION!r}"
    )
