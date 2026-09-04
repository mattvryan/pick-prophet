"""M12 model registry and promotion gate."""

from pick_prophet.registry.bootstrap import bootstrap_m12_v1, bootstrap_summary
from pick_prophet.registry.evaluate import CandidatePackage, evaluate_candidate
from pick_prophet.registry.store import RegistryStore
from pick_prophet.registry.transitions import (
    approve,
    designate_shadow,
    register_candidate,
    retire,
)

__all__ = [
    "CandidatePackage",
    "RegistryStore",
    "approve",
    "bootstrap_m12_v1",
    "bootstrap_summary",
    "designate_shadow",
    "evaluate_candidate",
    "register_candidate",
    "retire",
]
