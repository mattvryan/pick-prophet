"""Canonical JSON model bundles for M08 residual fits."""

from __future__ import annotations

import hashlib
import json
from typing import Any

BUNDLE_SCHEMA_VERSION = "1.0.0"


def canonical_json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def bundle_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def validate_bundle(payload: dict[str, Any]) -> None:
    required = {
        "bundle_schema_version",
        "variant",
        "fold_id",
        "beta",
        "feature_names",
        "lam",
        "protocol_version",
        "matrix_schema_version",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"bundle missing fields: {sorted(missing)}")
    if payload["bundle_schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported bundle schema {payload['bundle_schema_version']!r}"
        )
    if len(payload["beta"]) != len(payload["feature_names"]):
        raise ValueError("beta length must match feature_names")


def write_bundle(path: Any, payload: dict[str, Any]) -> str:
    validate_bundle(payload)
    text = canonical_json_dumps(payload) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_bundle(path: Any, *, expected_sha256: str | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("bundle hash mismatch")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("bundle must be an object")
    unknown = set(payload) - {
        "bundle_schema_version",
        "variant",
        "fold_id",
        "test_season",
        "train_seasons",
        "beta",
        "feature_names",
        "source_columns",
        "preprocessor",
        "lam",
        "solver",
        "max_iter",
        "ftol",
        "gtol",
        "nit",
        "fun",
        "message",
        "protocol_version",
        "matrix_schema_version",
        "scipy_version",
    }
    if unknown:
        raise ValueError(f"unknown bundle fields: {sorted(unknown)}")
    validate_bundle(payload)
    return payload
