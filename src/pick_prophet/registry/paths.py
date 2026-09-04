"""Safe repo-relative path handling for M12 registry references."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class UnsafeRegistryPathError(ValueError):
    """Raised when a path escapes approved roots or uses unsafe forms."""


DEFAULT_ALLOWED_ROOTS = (
    "docs/modeling_artifacts/",
    "artifacts/",
    "data/processed/",
)


def normalize_repo_path(
    path: str | Path,
    *,
    repo_root: Path,
    allowed_roots: tuple[str, ...] = DEFAULT_ALLOWED_ROOTS,
) -> str:
    raw = str(path)
    if not raw or raw.startswith("/") or PurePosixPath(raw).is_absolute():
        raise UnsafeRegistryPathError(f"absolute paths are forbidden: {raw!r}")
    posix = PurePosixPath(raw.replace("\\", "/"))
    if ".." in posix.parts or posix.parts[:1] == ("",):
        raise UnsafeRegistryPathError(f"path traversal is forbidden: {raw!r}")
    normalized = posix.as_posix()
    if not any(
        normalized == root.rstrip("/") or normalized.startswith(root)
        for root in allowed_roots
    ):
        raise UnsafeRegistryPathError(
            f"path outside approved roots {allowed_roots}: {normalized!r}"
        )
    resolved = (repo_root / normalized).resolve()
    repo_resolved = repo_root.resolve()
    try:
        resolved.relative_to(repo_resolved)
    except ValueError as exc:
        raise UnsafeRegistryPathError(
            f"path resolves outside repo root: {normalized!r}"
        ) from exc
    if resolved.is_symlink():
        link_target = resolved.resolve()
        try:
            link_target.relative_to(repo_resolved)
        except ValueError as exc:
            raise UnsafeRegistryPathError(
                f"symlink escapes repo root: {normalized!r}"
            ) from exc
        rel = link_target.relative_to(repo_resolved).as_posix()
        if not any(rel == root.rstrip("/") or rel.startswith(root) for root in allowed_roots):
            raise UnsafeRegistryPathError(
                f"symlink target outside approved roots: {normalized!r} -> {rel!r}"
            )
    return normalized


def resolve_safe(
    path: str,
    *,
    repo_root: Path,
    allowed_roots: tuple[str, ...] = DEFAULT_ALLOWED_ROOTS,
) -> Path:
    normalized = normalize_repo_path(
        path, repo_root=repo_root, allowed_roots=allowed_roots
    )
    return (repo_root / normalized).resolve()
