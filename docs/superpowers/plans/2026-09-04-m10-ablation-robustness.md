# M10 Ablation and Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an ablation/robustness runner over the M08 fixed-offset stack with compact paired evidence, season-drop aggregation, and a human decision worksheet (`recommendation` unset).

**Architecture:** Extended source-column variant registry → generalized M08 walk-forward (injectable variants) → compact scorers reusing M09 bootstrap/calibration → decision worksheet + report skeleton. No new estimator; no auto-promotion.

**Tech Stack:** Existing NumPy/SciPy residual stack, M09 cluster bootstrap, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-m10-ablation-robustness-design.md`

## Global Constraints

- Same M08 estimator/preprocess/λ/eligibility; identical canonical test IDs or fail
- Single-feature = source column (not one-hot levels); families + LOF as specified
- No prohibited/deferred columns; no HP search; no auto recommendation fill
- Season-drop = aggregate existing held-out preds only (not retrain)
- Anomalous season: 2020; ESPN min n = 50 → `insufficient`
- Large row-level outputs gitignored under `artifacts/residual_ablation/`
- Commit compact CSVs/JSON + `docs/incremental_value_report.md`

## File map

| File | Role |
|---|---|
| `src/pick_prophet/models/residual_ablation_variants.py` | Ablation variant registry |
| `src/pick_prophet/models/residual_fit.py` | Accept optional `variants=` |
| `src/pick_prophet/models/residual_ablation.py` | Runner: fit → score → worksheet/report |
| `src/pick_prophet/cli.py` | `ablate-residual` |
| `.gitignore` | `artifacts/residual_ablation/` |
| `tests/test_residual_ablation*.py` | Registry + runner tests |
| `docs/incremental_value_report.md` | Report template / regenerated compact summary |
| roadmap / market card pointers | Status |

---

### Task 1: Ablation variant registry

**Files:** `residual_ablation_variants.py`, `tests/test_residual_ablation_variants.py`, design/plan docs on branch

**Interfaces:**
- `MIN_ESPN_N = 50`
- `ANOMALOUS_SEASONS = (2020,)`
- `build_ablation_variants() -> dict[str, tuple[str, ...]]`
- `assert_ablation_variants_valid()`
- Helpers: `single_feature_ids()`, `family_ids()`, `lof_ids()`

Rules: singles = ordered union of three M08 families; LOF = combined − family; categoricals listed as source cols only; ban prohibited/deferred.

- [ ] Branch `modeling/m10-ablation-robustness`; commit design+plan
- [ ] TDD registry membership / LOF / bans
- [ ] Commit

---

### Task 2: Injectable variants + ablation runner + CLI

**Files:** `residual_fit.py`, `residual_ablation.py`, `cli.py`, `tests/test_residual_ablation.py`, `.gitignore`

**Interfaces:**
```python
def fit_residual_walkforward(..., variants: dict[str, tuple[str, ...]] | None = None) -> dict

def season_drop_metrics(predictions_rows, *, drop_season: int, market_model="market_only", candidate: str) -> dict

def run_ablation(matrix_path, out_dir, *, protocol_version="1.0.0", variants=None, n_boot=None, write_report_path=None) -> dict[str, Path]
```

Behaviors:
1. Fit all ablation variants (or test subset) with shared eligibility; fail on ID mismatch
2. Write gitignored preds under `out_dir/predictions/` (or similar)
3. Compact aggregates in `out_dir/compact/` (and optional copy path for committed fixtures in tests)
4. Score Δ vs market_only; bootstrap primary aggregate contrasts; calibration summary; slices with ESPN insufficient; season-drop + anomalous 2020; coverage/missingness
5. `decision_worksheet.csv` with empty `recommendation`
6. CLI `ablate-residual`

Tests use tiny matrix + small `variants=` override including synthetic helpful/noise/single-season columns (add columns only in fixture matrix / override registry for those tests).

- [ ] Implement + tests
- [ ] Commit

---

### Task 3: Docs, roadmap, verify, PR

- [ ] `docs/incremental_value_report.md` skeleton + human-review section
- [ ] Update roadmap M10; pointer from market residual doc
- [ ] Full pytest + ruff; open PR

---

## Self-review vs spec

Registry/LOF/singles, injectable M08 fit, season-drop aggregation, ESPN insufficient, blank recommendations, gitignore large arts, compact report — tasked. No TBD.
