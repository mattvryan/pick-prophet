"""Canonical JSON hashing for M12 registry records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_dumps(obj: Mapping[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_sha256(payload: Mapping[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "record_sha256"}
    return sha256_bytes(canonical_dumps(body).encode("utf-8"))


def attach_record_sha256(payload: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("record_sha256", None)
    out["record_sha256"] = record_sha256(out)
    return out


def assert_record_sha256(payload: Mapping[str, Any]) -> None:
    expected = payload.get("record_sha256")
    if not isinstance(expected, str) or not expected:
        raise ValueError("record missing record_sha256")
    actual = record_sha256(payload)
    if actual != expected:
        raise ValueError(
            f"record_sha256 mismatch: expected {expected}, recomputed {actual}"
        )
