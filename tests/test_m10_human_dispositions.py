"""M10 human dispositions: worksheet/report agreement and M11 fail-closed gate."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

import pytest

from pick_prophet.models.approved_feature_set import (
    EmptyPromotedFeaturesError,
    load_approved_feature_set,
    require_promoted_features_for_m11,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "docs" / "modeling_artifacts" / "m10" / "1.0.0"
WORKSHEET = ARTIFACT_DIR / "decision_worksheet.csv"
APPROVED = ARTIFACT_DIR / "approved_feature_set.json"
REPORT = ROOT / "docs" / "incremental_value_report.md"
MANIFEST = ARTIFACT_DIR / "manifest.json"

DECISION_TABLE_RE = re.compile(
    r"<!-- m10-human-dispositions-begin -->\n"
    r"\| unit_id \| decision \|\n\| --- \| --- \|\n"
    r"(?P<body>(?:\| [^|]+ \| [^|]+ \|\n)+)"
    r"<!-- m10-human-dispositions-end -->",
    re.MULTILINE,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worksheet_decisions() -> dict[str, str]:
    with WORKSHEET.open(newline="") as handle:
        return {
            row["unit_id"]: row["recommendation"]
            for row in csv.DictReader(handle)
        }


def _markdown_decisions() -> dict[str, str]:
    text = REPORT.read_text()
    match = DECISION_TABLE_RE.search(text)
    assert match is not None, "Human dispositions decision table missing from report"
    out: dict[str, str] = {}
    for line in match.group("body").strip().splitlines():
        parts = [p.strip() for p in line.strip("|").split("|")]
        assert len(parts) == 2, line
        out[parts[0]] = parts[1]
    return out


def test_worksheet_and_markdown_decisions_agree_exactly() -> None:
    worksheet = _worksheet_decisions()
    markdown = _markdown_decisions()
    assert worksheet == markdown
    assert worksheet, "expected disposition rows"


def test_approved_feature_set_matches_worksheet_and_hashes() -> None:
    decisions = _worksheet_decisions()
    approved = load_approved_feature_set(APPROVED)

    assert approved["status"] == "no_features_promoted"
    assert approved["promoted_features"] == []
    assert approved["review_only_features"] == ["home_sos"]
    assert approved["review_only_families"] == ["market_context"]
    assert decisions["single__home_sos"] == "review_only"
    assert decisions["family__market_context"] == "review_only"
    assert decisions["combined"] == "reject"
    assert decisions["family__site_temporal"] == "reject"
    assert decisions["family__history"] == "reject"
    assert all(
        decisions[uid] == "not_applicable"
        for uid in decisions
        if uid.startswith("lof__")
    )
    assert all(
        decisions[uid] == "reject"
        for uid, status in decisions.items()
        if uid.startswith("single__") and uid != "single__home_sos"
    )
    # Opening/movement fields stay unavailable — not present as reject rows.
    for feature in approved["unavailable_features"]:
        assert f"single__{feature}" not in decisions

    assert approved["evidence_manifest_sha256"] == _sha256(MANIFEST)
    assert approved["decision_worksheet_sha256"] == _sha256(WORKSHEET)
    assert approved["m11_blocked"] is True


def test_m11_fails_closed_when_promoted_features_empty() -> None:
    approved = load_approved_feature_set(APPROVED)
    assert approved["promoted_features"] == []

    with pytest.raises(EmptyPromotedFeaturesError, match="fail closed"):
        require_promoted_features_for_m11(approved)

    with pytest.raises(EmptyPromotedFeaturesError):
        require_promoted_features_for_m11({"promoted_features": []})


def test_m11_allows_baseline_only_when_explicitly_permitted() -> None:
    features = require_promoted_features_for_m11(
        {"promoted_features": []},
        allow_baseline_only=True,
    )
    assert features == []


def test_m11_returns_promoted_features_when_present() -> None:
    features = require_promoted_features_for_m11(
        {"promoted_features": ["home_sos"]},
    )
    assert features == ["home_sos"]
