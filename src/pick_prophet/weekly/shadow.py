"""Weekly experimental shadow runs (read-only w.r.t. production artifacts)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pick_prophet.registry.hashing import canonical_dumps, sha256_file
from pick_prophet.registry.store import RegistryStore
from pick_prophet.weekly.recommend import (
    apply_market_snapshot,
    build_recommendation_rows,
)
from pick_prophet.weekly.shadow_select import (
    ShadowSelectionError,
    select_shadow_model,
)
from pick_prophet.weekly.shadow_serving import (
    get_scorer,
    load_registry_bundle,
)
from pick_prophet.weekly.validate import parse_timestamp, validate_slate

SHADOW_SCHEMA_VERSION = "weekly_shadow.v1"
PROTECTED_NAMES = frozenset(
    {
        "final_card.md",
        "submission.json",
        "FINALIZED",
    }
)


class ShadowRunError(ValueError):
    """Fail-closed weekly shadow runner error."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _game_id_digest(game_ids: Sequence[str]) -> str:
    payload = ",".join(sorted(str(g) for g in game_ids))
    return _sha256_text(payload)


def _resolve_output_dir(output_dir: Path, *, repo_root: Path | None = None) -> Path:
    resolved = output_dir.expanduser()
    if not resolved.is_absolute():
        base = repo_root.resolve() if repo_root else Path.cwd().resolve()
        resolved = (base / resolved).resolve()
    else:
        resolved = resolved.resolve()
    return resolved


def assert_safe_shadow_output_dir(output_dir: Path, *, week_dir: Path | None) -> None:
    """Refuse protected production destinations."""
    resolved = output_dir.resolve()
    name = resolved.name
    if name in {"recommendations", "recommendations-current"}:
        raise ShadowRunError(
            f"refusing to use production recommendations directory: {resolved}"
        )
    if week_dir is not None:
        week_resolved = week_dir.resolve()
        if resolved == week_resolved:
            raise ShadowRunError(
                "refusing to write shadow pack into week root "
                "(holds final_card/submission)"
            )
        for protected in PROTECTED_NAMES:
            candidate = week_resolved / protected
            if resolved == candidate.resolve() or str(resolved).startswith(
                str(candidate.resolve()) + os.sep
            ):
                raise ShadowRunError(f"refusing protected path: {protected}")
    if resolved.exists() and any(resolved.iterdir()):
        raise ShadowRunError(
            f"refusing to write into non-empty output directory: {resolved}"
        )


def _assert_pit_market_rows(
    rows: Sequence[Mapping[str, Any]], *, as_of: str
) -> None:
    as_of_dt = parse_timestamp(as_of, "as_of", "shadow")
    for row in rows:
        lock = parse_timestamp(str(row["lock_at_utc"]), "lock_at_utc", "slate")
        cutoff = min(as_of_dt, lock)
        # Market fields on the slate are treated as available at capture/as-of;
        # require lock/as-of already validated by validate_slate, and reject
        # naive/missing lock (validate_slate already enforces).
        if cutoff.tzinfo is None:
            raise ShadowRunError("timezone-naive cutoff is forbidden")


def run_weekly_shadow(
    *,
    slate_path: Path | str,
    as_of: str,
    output_dir: Path | str,
    market_path: Path | str | None = None,
    registry_root: Path | str = "docs/modeling_artifacts/m12/1.0.0",
    repo_root: Path | str = ".",
    model_id: str | None = None,
    protocol_version: str = "1.0.0",
    matrix_schema_version: str = "1.0.0",
    feature_frame: Sequence[Mapping[str, Any]] | None = None,
    adjustments_path: Path | str | None = None,
    generation_timestamp: str | None = None,
) -> dict[str, Path]:
    """Run an experimental shadow compare pack (never mutates production card)."""
    slate_path = Path(slate_path)
    repo_root = Path(repo_root).resolve()
    registry_root = Path(registry_root)
    if not registry_root.is_absolute():
        registry_root = (repo_root / registry_root).resolve()
    else:
        registry_root = registry_root.resolve()
    week_dir = slate_path.parent
    out = _resolve_output_dir(Path(output_dir), repo_root=repo_root)
    assert_safe_shadow_output_dir(out, week_dir=week_dir)

    # Snapshot protected production bytes for callers/tests.
    protected_hashes = {
        name: sha256_file(week_dir / name)
        for name in PROTECTED_NAMES
        if (week_dir / name).is_file()
    }

    parse_timestamp(as_of, "as_of", "shadow")
    result = validate_slate(slate_path, as_of=as_of)
    if not result.ok:
        raise ShadowRunError("slate validation failed:\n" + "\n".join(result.errors))

    store = RegistryStore(root=registry_root, repo_root=repo_root)
    store.validate()
    selection = select_shadow_model(
        store,
        model_id=model_id,
        protocol_version=protocol_version,
        matrix_schema_version=matrix_schema_version,
    )

    input_rows = (
        apply_market_snapshot(result.rows, market_path)
        if market_path
        else list(result.rows)
    )
    _assert_pit_market_rows(input_rows, as_of=as_of)
    market_rows = build_recommendation_rows(input_rows)
    game_ids = [str(r["cfbd_game_id"]) for r in market_rows]

    ml_scores = None
    registry_snapshot: dict[str, Any] = {"tips": {}}
    for mid, sha in (store.load_index().get("tips") or {}).items():
        entry = store.load_entry(str(sha))
        registry_snapshot["tips"][str(mid)] = {
            "tip_sha256": str(sha),
            "model_type": entry["model_type"],
            "status": entry["status"],
            "model_id": entry["model_id"],
            "record_sha256": entry["record_sha256"],
        }

    if selection.status == "ml_shadow":
        assert selection.entry is not None and selection.tip_sha256 is not None
        tip = store.tip(selection.entry["model_id"])
        if tip != selection.tip_sha256:
            raise ShadowRunError("stale registry tip during shadow run")
        if feature_frame is None:
            raise ShadowRunError(
                "ml_shadow requires a feature_frame (PIT feature builder input)"
            )
        bundle_path, bundle_sha = load_registry_bundle(
            repo_root=repo_root, registry_entry=selection.entry
        )
        scorer = get_scorer(str(selection.entry["model_type"]))
        ml_scores = scorer.score(
            market_rows,
            as_of=as_of,
            feature_frame=feature_frame,
            registry_entry=selection.entry,
            bundle_path=bundle_path,
            expected_bundle_sha256=bundle_sha,
        )
        registry_snapshot["selected"] = {
            "model_id": selection.entry["model_id"],
            "tip_sha256": selection.tip_sha256,
            "bundle_path": selection.entry.get("bundle_path"),
            "bundle_sha256": selection.entry.get("bundle_sha256"),
            "approval_record_sha256": selection.entry.get("approval_record_sha256"),
            "entry": selection.entry,
        }

    adjustments: dict[str, str] = {}
    if adjustments_path is not None:
        adj_path = Path(adjustments_path)
        with adj_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                adjustments[str(row["cfbd_game_id"])] = str(row.get("adjustment") or "")

    generated_at = generation_timestamp or datetime.now(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    staging_parent = out.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{out.name}.staging.", dir=str(staging_parent))
    )
    try:
        compare_rows: list[dict[str, Any]] = []
        shadow_by_id = {
            g.game_id: g for g in (ml_scores.games if ml_scores else [])
        }
        for row in market_rows:
            gid = str(row["cfbd_game_id"])
            shadow = shadow_by_id.get(gid)
            market_pick = row.get("baseline_pick")
            shadow_pick = shadow.pick if shadow else None
            disagree = None
            if shadow_pick is not None and market_pick is not None:
                disagree = shadow_pick != market_pick
            compare_rows.append(
                {
                    "display_order": row["display_order"],
                    "cfbd_game_id": gid,
                    "away_team": row["away_team"],
                    "home_team": row["home_team"],
                    "market_pick": market_pick or "",
                    "market_pick_probability": row.get("baseline_pick_probability"),
                    "market_home_probability": row.get("home_market_probability"),
                    "shadow_pick": shadow_pick or "",
                    "shadow_pick_probability": (
                        shadow.pick_probability if shadow else ""
                    ),
                    "shadow_home_probability": shadow.p_home if shadow else "",
                    "shadow_status": shadow.status if shadow else "",
                    "disagreement": (
                        ""
                        if disagree is None
                        else ("true" if disagree else "false")
                    ),
                    "adjustment": adjustments.get(gid, ""),
                    "warning": shadow.warning
                    if shadow and shadow.warning
                    else (row.get("warning") or ""),
                }
            )

        compare_path = staging / "shadow_compare.csv"
        fieldnames = list(compare_rows[0].keys()) if compare_rows else [
            "cfbd_game_id",
            "market_pick",
            "shadow_pick",
        ]
        with compare_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in compare_rows:
                serialized = {
                    k: ""
                    if v is None
                    else (f"{v:.10f}".rstrip("0").rstrip(".") if isinstance(v, float) else v)
                    for k, v in row.items()
                }
                writer.writerow(serialized)

        manifest = {
            "artifact_schema_version": SHADOW_SCHEMA_VERSION,
            "label": "experimental",
            "status": selection.status,
            "reason": selection.reason,
            "protocol_version": protocol_version,
            "matrix_schema_version": matrix_schema_version,
            "as_of": as_of,
            "generation_timestamp": generated_at,
            "slate_path": str(slate_path),
            "slate_sha256": sha256_file(slate_path),
            "market_path": str(market_path) if market_path else None,
            "market_sha256": sha256_file(Path(market_path)) if market_path else None,
            "registry_root": str(registry_root.relative_to(repo_root))
            if str(registry_root).startswith(str(repo_root))
            else str(registry_root),
            "selected_model_id": (
                selection.entry["model_id"] if selection.entry else None
            ),
            "selected_tip_sha256": selection.tip_sha256,
            "ml_bundle_sha256": ml_scores.bundle_sha256 if ml_scores else None,
            "game_id_digest": _game_id_digest(game_ids),
            "game_count": len(game_ids),
            "notes": (
                "Experimental shadow pack. Does not alter final_card, "
                "submission, or production recommendations. "
                + (
                    "ML columns are null because no eligible non-baseline tip exists."
                    if selection.status == "no_ml_shadow"
                    else "ML shadow scores from registry tip."
                )
            ),
        }
        (staging / "shadow_manifest.json").write_text(
            canonical_dumps(manifest) + "\n", encoding="utf-8"
        )
        (staging / "registry_snapshot.json").write_text(
            canonical_dumps(registry_snapshot) + "\n", encoding="utf-8"
        )
        input_manifest = {
            "artifact_schema_version": "weekly_shadow_input.v1",
            "game_id_digest": manifest["game_id_digest"],
            "game_ids": game_ids,
            "slate_sha256": manifest["slate_sha256"],
            "market_sha256": manifest["market_sha256"],
            "as_of": as_of,
            "feature_frame_provided": feature_frame is not None,
            "feature_columns": sorted(
                {
                    k
                    for row in (feature_frame or [])
                    for k in row
                    if k
                    not in {
                        "cfbd_game_id",
                        "game_id",
                        "home_team",
                        "away_team",
                    }
                }
            ),
            "pit_audit": "validate_slate+as_of/lock cutoff; no post-as-of refresh",
        }
        (staging / "input_manifest.json").write_text(
            canonical_dumps(input_manifest) + "\n", encoding="utf-8"
        )

        card_lines = [
            "# Experimental shadow card",
            "",
            "**Label:** experimental / non-production",
            f"**Status:** `{selection.status}`",
            f"**As of:** `{as_of}`",
            "",
        ]
        if selection.status == "no_ml_shadow":
            card_lines.append(
                "No compatible non-baseline shadow/approved tip is registered. "
                "Market reference rows are shown; ML shadow columns are empty."
            )
            card_lines.append("")
        card_lines.append("| Order | Game | Market pick | Shadow pick | Disagree |")
        card_lines.append("| --- | --- | --- | --- | --- |")
        for row in compare_rows:
            card_lines.append(
                f"| {row['display_order']} | {row['away_team']} @ {row['home_team']} | "
                f"{row['market_pick']} | {row['shadow_pick'] or '—'} | "
                f"{row['disagreement'] or '—'} |"
            )
        (staging / "shadow_card.md").write_text(
            "\n".join(card_lines) + "\n", encoding="utf-8"
        )

        # Exclusive publish: directory must not exist.
        try:
            os.mkdir(out)
        except FileExistsError as exc:
            raise ShadowRunError(
                f"output run directory already exists: {out}"
            ) from exc
        for item in staging.iterdir():
            target = out / item.name
            shutil.move(str(item), str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # Verify production immutability.
    for name, before in protected_hashes.items():
        path = week_dir / name
        if not path.is_file() or sha256_file(path) != before:
            raise ShadowRunError(
                f"production artifact mutated during shadow run: {name}"
            )

    return {
        "shadow_manifest": out / "shadow_manifest.json",
        "shadow_compare": out / "shadow_compare.csv",
        "shadow_card": out / "shadow_card.md",
        "registry_snapshot": out / "registry_snapshot.json",
        "input_manifest": out / "input_manifest.json",
        "output_dir": out,
    }


def load_shadow_pack(shadow_dir: Path) -> dict[str, Any]:
    """Load and validate a complete experimental shadow pack for grading."""
    shadow_dir = Path(shadow_dir)
    required = [
        "shadow_manifest.json",
        "shadow_compare.csv",
        "shadow_card.md",
        "registry_snapshot.json",
        "input_manifest.json",
    ]
    missing = [name for name in required if not (shadow_dir / name).is_file()]
    if missing:
        raise ShadowRunError(
            f"incomplete shadow pack (ignored by grade): missing {missing}"
        )
    manifest = json.loads((shadow_dir / "shadow_manifest.json").read_text())
    if manifest.get("label") != "experimental":
        raise ShadowRunError("shadow pack missing experimental label")
    if manifest.get("artifact_schema_version") != SHADOW_SCHEMA_VERSION:
        raise ShadowRunError(
            f"unsupported shadow schema {manifest.get('artifact_schema_version')!r}"
        )
    return manifest


# Re-export for CLI error typing
__all__ = [
    "ShadowRunError",
    "ShadowSelectionError",
    "assert_safe_shadow_output_dir",
    "load_shadow_pack",
    "run_weekly_shadow",
]
