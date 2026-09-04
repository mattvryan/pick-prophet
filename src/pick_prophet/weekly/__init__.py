"""Weekly Pick'em operations: slate validation and market-baseline recommendations."""

from .recommend import OUTPUT_SCHEMA_VERSION, recommend
from .validate import ValidationResult, validate_slate

__all__ = [
    "OUTPUT_SCHEMA_VERSION",
    "ValidationResult",
    "recommend",
    "validate_slate",
]
