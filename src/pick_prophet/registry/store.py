"""Append-only registry store: exclusive writes, tip CAS, validate, list."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pick_prophet.registry.hashing import (
    assert_record_sha256,
    attach_record_sha256,
    canonical_dumps,
    sha256_file,
)
from pick_prophet.registry.paths import DEFAULT_ALLOWED_ROOTS, resolve_safe
from pick_prophet.registry.records import (
    LIFECYCLE_STATES,
    PERMITTED_TRANSITIONS,
    validate_entry_shape,
)

KIND_DIRS = {
    "entry": "entries",
    "evaluation": "evaluations",
    "approval": "approvals",
    "retirement": "retirements",
}

INDEX_NAME = "registry_index.json"
MANIFEST_NAME = "manifest.json"
POLICY_NAME = "promotion_policy.json"


class RegistryError(ValueError):
    """Base registry failure."""


class StaleTipError(RegistryError):
    """Compare-and-swap tip mismatch."""


class ImmutableRecordError(RegistryError):
    """Attempted overwrite of an existing content-addressed record."""


@dataclass
class RegistryStore:
    root: Path
    repo_root: Path
    allowed_roots: tuple[str, ...] = DEFAULT_ALLOWED_ROOTS

    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME

    def kind_dir(self, kind: str) -> Path:
        if kind not in KIND_DIRS:
            raise RegistryError(f"unknown record kind: {kind!r}")
        return self.root / KIND_DIRS[kind]

    def record_path(self, kind: str, record_sha256: str) -> Path:
        return self.kind_dir(kind) / f"{record_sha256}.json"

    def load_index(self) -> dict[str, Any]:
        path = self.index_path()
        if not path.exists():
            return {
                "artifact_schema_version": "1.0.0",
                "registry_version": "1.0.0",
                "tips": {},
                "models": {},
            }
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            raise RegistryError("registry_index.json must be an object")
        return payload

    def tip(self, model_id: str) -> str | None:
        tips = self.load_index().get("tips") or {}
        value = tips.get(model_id)
        return str(value) if value is not None else None

    def load_entry(self, record_sha256: str) -> dict[str, Any]:
        path = self.record_path("entry", record_sha256)
        if not path.exists():
            raise RegistryError(f"missing entry record: {record_sha256}")
        payload = json.loads(path.read_text())
        assert_record_sha256(payload)
        if payload["record_sha256"] != record_sha256:
            raise RegistryError(
                f"entry filename/hash mismatch: {record_sha256} vs "
                f"{payload['record_sha256']}"
            )
        validate_entry_shape(payload)
        return payload

    def load_kind(self, kind: str, record_sha256: str) -> dict[str, Any]:
        path = self.record_path(kind, record_sha256)
        if not path.exists():
            raise RegistryError(f"missing {kind} record: {record_sha256}")
        payload = json.loads(path.read_text())
        assert_record_sha256(payload)
        if payload["record_sha256"] != record_sha256:
            raise RegistryError(f"{kind} filename/hash mismatch")
        return payload

    def write_record(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = attach_record_sha256(payload)
        assert_record_sha256(record)
        digest = record["record_sha256"]
        directory = self.kind_dir(kind)
        directory.mkdir(parents=True, exist_ok=True)
        path = self.record_path(kind, digest)
        data = canonical_dumps(record) + "\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(path, flags, 0o644)
        except FileExistsError as exc:
            existing = path.read_text()
            if existing != data:
                raise ImmutableRecordError(
                    f"refusing to mutate existing {kind} record {digest}"
                ) from exc
            return record
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return record

    def cas_set_tip(
        self,
        model_id: str,
        *,
        expected_tip: str | None,
        new_tip: str,
        model_meta: dict[str, Any] | None = None,
    ) -> None:
        index = self.load_index()
        tips = dict(index.get("tips") or {})
        current = tips.get(model_id)
        if current != expected_tip:
            raise StaleTipError(
                f"stale tip for {model_id}: expected {expected_tip!r}, "
                f"found {current!r}"
            )
        tips[model_id] = new_tip
        index["tips"] = tips
        models = dict(index.get("models") or {})
        meta = dict(models.get(model_id) or {})
        if model_meta:
            meta.update(model_meta)
        meta["tip_sha256"] = new_tip
        models[model_id] = meta
        index["models"] = models
        self._atomic_write_json(self.index_path(), index)

    def rewrite_manifest(self) -> dict[str, Any]:
        artifacts: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if rel == MANIFEST_NAME:
                continue
            artifacts[rel] = sha256_file(path)
        manifest = {
            "artifact_schema_version": "1.0.0",
            "registry_version": "1.0.0",
            "pack_version": "1.0.0",
            "artifacts_sha256": artifacts,
            "excludes_self": True,
        }
        self._atomic_write_json(self.manifest_path(), manifest)
        return manifest

    def validate(self) -> None:
        if not self.root.is_dir():
            raise RegistryError(f"registry root missing: {self.root}")
        index = self.load_index()
        tips = dict(index.get("tips") or {})
        seen_versions: set[tuple[str, str]] = set()
        for model_id, tip_sha in tips.items():
            entry = self.load_entry(str(tip_sha))
            if entry["model_id"] != model_id:
                raise RegistryError(
                    f"tip model_id mismatch for {model_id}: {entry['model_id']}"
                )
            self._validate_lineage(entry, seen_versions)
            self._validate_referenced_artifacts(entry)
        # orphan action-record reachability: every approval/retirement referenced
        referenced = set()
        for tip_sha in tips.values():
            referenced |= self._collect_action_refs(str(tip_sha))
        for kind in ("approval", "retirement", "evaluation"):
            directory = self.kind_dir(kind)
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                digest = path.stem
                payload = self.load_kind(kind, digest)
                if kind in {"approval", "retirement"} and digest not in referenced:
                    raise RegistryError(
                        f"orphaned {kind} record not reachable from tips: "
                        f"{digest}"
                    )
                _ = payload
        manifest_path = self.manifest_path()
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            artifacts = dict(manifest.get("artifacts_sha256") or {})
            if MANIFEST_NAME in artifacts:
                raise RegistryError("manifest must exclude itself from digest map")
            for rel, expected in artifacts.items():
                path = self.root / rel
                if not path.is_file():
                    raise RegistryError(f"manifest references missing file: {rel}")
                actual = sha256_file(path)
                if actual != expected:
                    raise RegistryError(
                        f"manifest hash mismatch for {rel}: "
                        f"expected {expected}, got {actual}"
                    )
            # every file except manifest must be covered
            for path in self.root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(self.root).as_posix()
                if rel == MANIFEST_NAME:
                    continue
                if rel not in artifacts:
                    raise RegistryError(f"pack file missing from manifest: {rel}")

    def list_models(self) -> list[dict[str, Any]]:
        self.validate()
        rows: list[dict[str, Any]] = []
        for model_id, tip_sha in sorted((self.load_index().get("tips") or {}).items()):
            entry = self.load_entry(str(tip_sha))
            rows.append(
                {
                    "model_id": model_id,
                    "status": entry["status"],
                    "model_type": entry["model_type"],
                    "model_version": entry["model_version"],
                    "tip_sha256": tip_sha,
                }
            )
        return rows

    def _validate_lineage(
        self,
        tip_entry: dict[str, Any],
        seen_versions: set[tuple[str, str]],
    ) -> None:
        visited: set[str] = set()
        current: dict[str, Any] | None = tip_entry
        previous_status: str | None = None
        while current is not None:
            digest = current["record_sha256"]
            if digest in visited:
                raise RegistryError(f"lineage cycle detected at {digest}")
            visited.add(digest)
            key = (current["model_id"], current["model_version"])
            # duplicate version only illegal across distinct genesis lineages;
            # same lineage may keep model_version while changing status.
            if previous_status is None:
                if key in seen_versions:
                    raise RegistryError(
                        f"duplicate model_id/version tip conflict: {key}"
                    )
                seen_versions.add(key)
            status = current["status"]
            if status not in LIFECYCLE_STATES:
                raise RegistryError(f"unknown status in lineage: {status!r}")
            prior = current.get("prior_record_sha256")
            if prior is None:
                from_status = None
            else:
                prior_entry = self.load_entry(str(prior))
                from_status = prior_entry["status"]
                if (from_status, status) not in PERMITTED_TRANSITIONS:
                    raise RegistryError(
                        f"illegal transition {from_status!r} -> {status!r} "
                        f"for {digest}"
                    )
                current = prior_entry
                previous_status = status
                continue
            if (None, status) not in PERMITTED_TRANSITIONS:
                raise RegistryError(f"illegal genesis status {status!r}")
            # bootstrap exception for approved genesis
            if status == "approved":
                if current["model_type"] != "market_baseline":
                    raise RegistryError(
                        "approved genesis only permitted for market_baseline"
                    )
                if current["model_id"] != "market_only":
                    raise RegistryError(
                        "approved genesis only permitted for model_id=market_only"
                    )
                approval = self.load_kind(
                    "approval", str(current["approval_record_sha256"])
                )
                if approval.get("approval_kind") != "bootstrap_baseline":
                    raise RegistryError(
                        "approved genesis requires bootstrap_baseline approval"
                    )
            current = None

    def _collect_action_refs(self, tip_sha: str) -> set[str]:
        refs: set[str] = set()
        current_sha: str | None = tip_sha
        while current_sha:
            entry = self.load_entry(current_sha)
            for key in (
                "approval_record_sha256",
                "retirement_record_sha256",
                "evaluation_record_sha256",
            ):
                value = entry.get(key)
                if value:
                    refs.add(str(value))
            prior = entry.get("prior_record_sha256")
            current_sha = str(prior) if prior else None
        return refs

    def _validate_referenced_artifacts(self, entry: dict[str, Any]) -> None:
        for path_key, hash_key in (
            ("m10_approved_feature_set_path", "m10_approved_feature_set_sha256"),
            ("m11_decision_path", "m11_decision_sha256"),
            ("bundle_path", "bundle_sha256"),
        ):
            path_value = entry.get(path_key)
            hash_value = entry.get(hash_key)
            if path_value is None and hash_value is None:
                continue
            if not path_value or not hash_value:
                raise RegistryError(
                    f"{entry['record_sha256']} incomplete path/hash pair "
                    f"{path_key}/{hash_key}"
                )
            resolved = resolve_safe(
                str(path_value),
                repo_root=self.repo_root,
                allowed_roots=self.allowed_roots,
            )
            if not resolved.is_file():
                raise RegistryError(f"missing referenced artifact: {path_value}")
            actual = sha256_file(resolved)
            if actual != hash_value:
                raise RegistryError(
                    f"tampered artifact {path_value}: expected {hash_value}, "
                    f"got {actual}"
                )
        approval_sha = entry.get("approval_record_sha256")
        if approval_sha:
            self.load_kind("approval", str(approval_sha))
        retirement_sha = entry.get("retirement_record_sha256")
        if retirement_sha:
            self.load_kind("retirement", str(retirement_sha))

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_dumps(payload) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def iter_pack_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path
