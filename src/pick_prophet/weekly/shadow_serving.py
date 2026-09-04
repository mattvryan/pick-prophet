"""Strict serving adapters for M13 weekly shadow scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from pick_prophet.models.fixed_offset_logit import sigmoid
from pick_prophet.models.residual_bundle import load_bundle
from pick_prophet.registry.hashing import sha256_file
from pick_prophet.registry.paths import normalize_repo_path, resolve_safe

ALLOWED_BUNDLE_SUFFIXES = (".json",)


class ShadowServingError(ValueError):
    """Fail-closed serving / scoring error."""


@dataclass
class ScoredGame:
    game_id: str
    p_home: float
    pick: str
    pick_probability: float
    status: str
    warning: str | None = None


@dataclass
class ShadowScoreResult:
    model_id: str
    model_type: str
    entry_sha256: str
    bundle_sha256: str
    games: list[ScoredGame]
    feature_parity_ok: bool
    missing_features: list[str] = field(default_factory=list)
    timing_notes: str | None = None


class ShadowScorer(Protocol):
    def score(
        self,
        slate_rows: Sequence[Mapping[str, Any]],
        *,
        as_of: str,
        feature_frame: Sequence[Mapping[str, Any]],
        registry_entry: Mapping[str, Any],
        bundle_path: Path,
        expected_bundle_sha256: str,
    ) -> ShadowScoreResult: ...


def assert_allowlisted_bundle_path(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_BUNDLE_SUFFIXES:
        raise ShadowServingError(
            f"unapproved bundle serialization {suffix!r}; "
            f"allowed={list(ALLOWED_BUNDLE_SUFFIXES)}"
        )
    name = path.name.lower()
    for banned in (".pkl", ".pickle", ".joblib", ".pt", ".pth", ".onnx"):
        if name.endswith(banned) or banned in name:
            raise ShadowServingError(
                f"executable/unapproved serialization rejected: {path}"
            )


def _game_id(row: Mapping[str, Any]) -> str:
    for key in ("cfbd_game_id", "game_id"):
        if key in row and row[key] not in (None, ""):
            return str(row[key])
    raise ShadowServingError("row missing canonical game id")


def _index_by_game_id(
    rows: Sequence[Mapping[str, Any]], *, label: str
) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        gid = _game_id(row)
        if gid in out:
            raise ShadowServingError(f"duplicate game_id in {label}: {gid}")
        out[gid] = row
    return out


def _pick_from_p_home(
    p_home: float, *, home_team: str, away_team: str
) -> tuple[str, float, str | None]:
    if not math.isfinite(p_home) or p_home < 0.0 or p_home > 1.0:
        raise ShadowServingError(f"probability out of [0,1] or nonfinite: {p_home}")
    if p_home > 0.5:
        return home_team, p_home, None
    if p_home < 0.5:
        return away_team, 1.0 - p_home, None
    # Deterministic tie rule at exactly 0.5: pick home.
    return home_team, p_home, "p_home exactly 0.5; deterministic pick=home"


class ResidualLogisticScorer:
    """Score allowlisted M08-style JSON bundles with fixed-offset logistic."""

    def score(
        self,
        slate_rows: Sequence[Mapping[str, Any]],
        *,
        as_of: str,
        feature_frame: Sequence[Mapping[str, Any]],
        registry_entry: Mapping[str, Any],
        bundle_path: Path,
        expected_bundle_sha256: str,
    ) -> ShadowScoreResult:
        del as_of  # PIT enforced by caller before invoke
        if registry_entry.get("model_type") != "residual_logistic":
            raise ShadowServingError(
                f"ResidualLogisticScorer got model_type="
                f"{registry_entry.get('model_type')!r}"
            )
        assert_allowlisted_bundle_path(bundle_path)
        actual = sha256_file(bundle_path)
        if actual != expected_bundle_sha256:
            raise ShadowServingError(
                f"bundle hash mismatch: expected {expected_bundle_sha256}, got {actual}"
            )
        bundle = load_bundle(bundle_path, expected_sha256=expected_bundle_sha256)
        feature_names = [str(x) for x in bundle["feature_names"]]
        beta = np.asarray(bundle["beta"], dtype=float)
        if len(beta) != len(feature_names):
            raise ShadowServingError("beta/feature_names length mismatch")

        # Serving accepts pre-transformed numeric columns matching feature_names
        # exactly (tests and future serving builders). Reject unknown extras that
        # look like undeclared model inputs beyond metadata keys.
        meta_keys = {
            "cfbd_game_id",
            "game_id",
            "home_team",
            "away_team",
            "home_market_logit",
            "home_market_probability",
            "available_as_of_utc",
            "source_retrieved_at_utc",
            "effective_at_utc",
        }
        slate_by_id = _index_by_game_id(slate_rows, label="slate")
        frame_by_id = _index_by_game_id(feature_frame, label="feature_frame")
        if set(frame_by_id) != set(slate_by_id):
            raise ShadowServingError(
                "feature_frame game IDs must exactly match slate game IDs"
            )

        missing_features: list[str] = []
        games: list[ScoredGame] = []
        for gid in sorted(slate_by_id, key=lambda x: int(x) if x.isdigit() else x):
            slate = slate_by_id[gid]
            feat = frame_by_id[gid]
            extras = set(feat) - meta_keys - set(feature_names)
            # allow source-column passthrough only if also listed in feature_set
            # of registry; still reject unknown transformed names
            undeclared = extras - set(registry_entry.get("feature_set") or [])
            if undeclared:
                raise ShadowServingError(
                    f"undeclared extra model inputs for game {gid}: "
                    f"{sorted(undeclared)}"
                )
            row_missing = [name for name in feature_names if name not in feat]
            if row_missing:
                missing_features = sorted(set(missing_features) | set(row_missing))
                continue
            try:
                offset = float(feat["home_market_logit"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ShadowServingError(
                    f"home_market_logit missing/invalid for game {gid}"
                ) from exc
            x = np.asarray([float(feat[name]) for name in feature_names], dtype=float)
            if not np.all(np.isfinite(x)):
                raise ShadowServingError(f"nonfinite features for game {gid}")
            eta = float(offset + float(x @ beta))
            p_home = float(sigmoid(eta))
            home = str(slate["home_team"])
            away = str(slate["away_team"])
            if str(feat.get("home_team", home)) != home or str(
                feat.get("away_team", away)
            ) != away:
                raise ShadowServingError(
                    f"home/away orientation mismatch for game {gid}"
                )
            pick, pick_p, warn = _pick_from_p_home(
                p_home, home_team=home, away_team=away
            )
            games.append(
                ScoredGame(
                    game_id=gid,
                    p_home=p_home,
                    pick=pick,
                    pick_probability=pick_p,
                    status="ok",
                    warning=warn,
                )
            )

        if missing_features:
            raise ShadowServingError(
                f"required features unavailable: {missing_features}"
            )
        if len(games) != len(slate_by_id):
            raise ShadowServingError("scorer did not emit exactly one row per game")

        return ShadowScoreResult(
            model_id=str(registry_entry["model_id"]),
            model_type="residual_logistic",
            entry_sha256=str(registry_entry["record_sha256"]),
            bundle_sha256=expected_bundle_sha256,
            games=games,
            feature_parity_ok=True,
            missing_features=[],
            timing_notes="caller-enforced PIT; residual scorer uses provided frame",
        )


class BoostedScorer:
    """Registered interface; M13 v1 has no boosted serving implementation."""

    def score(
        self,
        slate_rows: Sequence[Mapping[str, Any]],
        *,
        as_of: str,
        feature_frame: Sequence[Mapping[str, Any]],
        registry_entry: Mapping[str, Any],
        bundle_path: Path,
        expected_bundle_sha256: str,
    ) -> ShadowScoreResult:
        del slate_rows, as_of, feature_frame, bundle_path, expected_bundle_sha256
        raise ShadowServingError(
            f"boosted serving is not implemented in M13 v1 "
            f"(model_id={registry_entry.get('model_id')})"
        )


def get_scorer(model_type: str) -> ShadowScorer:
    if model_type == "residual_logistic":
        return ResidualLogisticScorer()
    if model_type == "boosted":
        return BoostedScorer()
    raise ShadowServingError(f"unsupported model_type for ML shadow: {model_type!r}")


def load_registry_bundle(
    *,
    repo_root: Path,
    registry_entry: Mapping[str, Any],
    allowed_roots: tuple[str, ...] | None = None,
) -> tuple[Path, str]:
    path_rel = registry_entry.get("bundle_path")
    digest = registry_entry.get("bundle_sha256")
    if not path_rel or not digest:
        raise ShadowServingError("registry entry missing bundle path/hash")
    kwargs: dict[str, Any] = {"repo_root": repo_root}
    if allowed_roots is not None:
        kwargs["allowed_roots"] = allowed_roots
    norm = normalize_repo_path(str(path_rel), **kwargs)
    resolved = resolve_safe(norm, **kwargs)
    assert_allowlisted_bundle_path(resolved)
    if not resolved.is_file():
        raise ShadowServingError(f"bundle missing: {norm}")
    actual = sha256_file(resolved)
    if actual != digest:
        raise ShadowServingError(
            f"bundle hash mismatch for {norm}: expected {digest}, got {actual}"
        )
    return resolved, str(digest)
