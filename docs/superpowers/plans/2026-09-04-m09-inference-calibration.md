# M09 Inference and Calibration Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship diagnostic-only inference/calibration reports over raw M08 residual `p_home`, with cluster-key bootstrap, Holm-controlled confirmatory log-loss deltas, reliability/calibration/flip/adjustment tables, and a CLI — without writing calibrated predictions.

**Architecture:** Load + validate M08 residual artifacts and the exact M07 matrix → pair each non-market variant to `market_only` → score metrics/slices → cluster-bootstrap with contrast-stable RNG → calibration GLM diagnostic → flip/adjustment bands → Holm across one global confirmatory family → write CSV/JSON/Markdown. Never mutate `p_home`.

**Tech Stack:** Python 3.11+, NumPy/SciPy (existing), pandas as needed for joins, existing `evaluation` metrics/protocol, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-m09-inference-calibration-design.md`

## Global Constraints

- Raw M08 `p_home` only; no calibrated candidate; no prediction rewrite
- Cluster key `(test_season, season_type, week)`; same clusters/rows for both arms
- `n_boot=500`, seed `20260904`, 95% percentile CI via deterministic linear quantiles of uncentered `Δ*`
- Centered-null bootstrap p: `p = (1 + #{|Δ* − Δ| ≥ |Δ|}) / (n_boot + 1)`
- Contrast-specific RNG: derive stream from protocol seed + stable contrast ID
- Holm once across estimable `(non-market variant × overall-or-required-slice)` log-loss Δ; dedupe identical game-ID sets; empty/non-estimable stay in inventory, not in Holm denominator
- Flip: home if `p > 0.5 + 1e-12`, away if `p < 0.5 - 1e-12`, else tie; flip only non-tie disagreements
- Adjustment bands on `|adjustment|` log-odds: `[0,0.05)`, `[0.05,0.15)`, `[0.15,0.30)`, `[0.30,∞)`
- Calibration: unpenalized Bernoulli GLM `y ~ σ(a + b logit(p_ε))`, `ε=1e-6`; status-coded failures; never alter preds
- Validate manifest hashes, unique keys, 1:1 joins, `p_home` agreement pred↔detail, matrix hash, finite `p∈[0,1]`
- Do not change legacy `bootstrap_paired_delta` week-only behavior
- Eligibility exclusions come from M08 `eligibility.csv`, not reinvented

## File map

| File | Role |
|---|---|
| `src/pick_prophet/evaluation/cluster_bootstrap.py` | Cluster-key paired bootstrap, percentile CI, centered p, contrast RNG |
| `src/pick_prophet/evaluation/holm.py` | Holm–Bonferroni step-down |
| `src/pick_prophet/models/residual_diagnostics.py` | Load/validate, pair, score, slices, cal/flips/bands, writers, orchestrator |
| `src/pick_prophet/cli.py` | `diagnose-residual` |
| `tests/test_cluster_bootstrap.py` | Bootstrap/CI/p/RNG tests |
| `tests/test_holm.py` | Holm + dedupe inventory tests |
| `tests/test_residual_diagnostics.py` | Integration + validation + CLI smoke |
| `docs/residual_diagnostics.md` | Operator card |
| `docs/market_residual_model.md` | Pointer to M09 |
| `docs/modeling_implementation_roadmap.md` | Mark M09 done when acceptance passes |
| Spec (already written) | Commit on branch |

---

### Task 1: Branch + design commit + cluster bootstrap + Holm

**Files:**
- Create: `src/pick_prophet/evaluation/cluster_bootstrap.py`
- Create: `src/pick_prophet/evaluation/holm.py`
- Create: `tests/test_cluster_bootstrap.py`
- Create: `tests/test_holm.py`
- Add: `docs/superpowers/specs/2026-09-04-m09-inference-calibration-design.md`
- Add: `docs/superpowers/plans/2026-09-04-m09-inference-calibration.md`

**Interfaces:**

```python
def contrast_rng(seed: int, contrast_id: str) -> random.Random: ...

def cluster_keys(
    test_seasons, season_types, weeks
) -> list[tuple[Any, Any, Any]]: ...

def bootstrap_paired_delta_clusters(
    clusters: Sequence[Any],
    y_true: Sequence[int],
    p_left: Sequence[float],
    p_right: Sequence[float],
    *,
    metric: str,
    n_boot: int = 500,
    seed: int = 20260904,
    contrast_id: str,
) -> dict[str, float]:
    """Return delta, mean_delta, ci_low, ci_high, p_value, n_boot, seed, n_clusters.
    Δ = metric(right) - metric(left). Percentile CI on uncentered Δ*.
    p_value uses centered null Δ* - Δ.
    """

def holm_adjust(p_values: Sequence[float | None], *, alpha: float = 0.05) -> list[dict]:
    """Skip None (non-estimable). Return raw_p, holm_p, rank, family_size, reject."""
```

- [ ] Create branch `modeling/m09-inference-calibration` from updated `main`
- [ ] Write failing tests:
  - same seed+contrast_id ⇒ identical samples; different contrast_id ⇒ different stream
  - week-only collision: two seasons same week number produce distinct clusters
  - paired arms always see identical resampled indices
  - known tiny fixture: percentile CI + centered p match hand calculation
  - Holm ordering/adjusted p on fixed p-vector; Nones excluded from family_size
- [ ] Implement helpers; run `pytest tests/test_cluster_bootstrap.py tests/test_holm.py -v`
- [ ] Commit: `Add M09 cluster bootstrap and Holm helpers`

---

### Task 2: Diagnostics core — load, validate, pair, score, artifacts

**Files:**
- Create: `src/pick_prophet/models/residual_diagnostics.py`
- Create: `tests/test_residual_diagnostics.py`
- Modify: `src/pick_prophet/cli.py`

**Interfaces:**

```python
PROB_AGREE_TOL = 1e-12
FLIP_EPS = 1e-12
CAL_EPS = 1e-6
ADJUSTMENT_BANDS = ((0.0, 0.05), (0.05, 0.15), (0.15, 0.30), (0.30, None))

def diagnose_residual(
    predictions_dir: Path,
    matrix_path: Path,
    out_dir: Path,
    *,
    protocol_version: str = "1.0.0",
) -> dict[str, Path]:
    """Validate inputs, compute all tables, write artifacts; never write predictions."""
```

Required behaviors (encode as tests first):

1. **Load/validate:** require `predictions.csv`, `residual_details.csv`, `eligibility.csv`, `run_manifest.json`; verify file SHAs vs manifest; matrix SHA vs `matrix_sha256`; unique `(model,fold_id,test_season,game_id)`; pred/detail `p_home` within `PROB_AGREE_TOL`; reject non-finite / out-of-`[0,1]` p; 1:1 matrix join on `game_id` with `season == test_season`; fail on duplicates / one-to-many / hash mismatch.
2. **Pairing:** for each non-`market_only` variant, pair to `market_only` on identical `(fold_id, game_id)` sets (aggregate pools held-out rows); unequal IDs → hard fail.
3. **Metrics:** overall + per-fold accuracy/log-loss/Brier and Δ vs market; aggregate = pooled rows not mean of folds.
4. **Slices:** M01 `required_slices` + `overall`; confirmatory inventory; dedupe identical game-ID sets for Holm (keep both labels in tables; one hypothesis).
5. **Bootstrap:** use Task 1 helper for accuracy/log-loss/Brier; Holm only on estimable confirmatory log-loss family across all variants×slices once.
6. **Reliability:** `calibration_bins` per variant aggregate and per fold; include empty bins.
7. **Calibration GLM:** deterministic unpenalized 2-param fit (SciPy L-BFGS-B or Newton on Bernoulli NLL); clip p only inside fit; emit `status`/`reason` when not estimable; never write new p.
8. **Flips/bands:** flip rules + `flip_summary.csv`; adjustment bands + mean `candidate_p - market_p`.
9. **Coverage:** copy/aggregate reason codes from M08 `eligibility.csv` into `exclusions.csv` / summary — do not invent exclusions.
10. **CLI:** `pick-prophet diagnose-residual --predictions-dir … --matrix … --out-dir … --protocol 1.0.0`
11. **Artifacts:** all files listed in the spec; `report.md` states raw preds unchanged / no calibrated candidate.

Fixture: tiny synthetic residual dir (2 seasons × 2 weeks × few games, `market_only` + one candidate, matrix with `season_type`/`neutral_site`/`spread_home`) under `tests/fixtures/residual_diagnostics/`.

- [ ] Write failing validation + scoring + CLI smoke tests
- [ ] Implement `residual_diagnostics.py` + CLI wiring
- [ ] Run `pytest tests/test_residual_diagnostics.py tests/test_cluster_bootstrap.py tests/test_holm.py -v`
- [ ] Commit: `Add diagnose-residual diagnostics pipeline`

---

### Task 3: Docs, roadmap, full verify, PR

**Files:**
- Create: `docs/residual_diagnostics.md`
- Modify: `docs/market_residual_model.md`
- Modify: `docs/modeling_implementation_roadmap.md` § M09

- [ ] Document constants, cluster key, centered p, Holm family, raw-only rule, CLI
- [ ] Point M08 model card to M09; mark roadmap checkboxes when tests pass
- [ ] Run full `pytest` + `ruff check`
- [ ] Open PR `modeling/m09-inference-calibration` → `main`

---

## Self-review vs spec

| Spec requirement | Task |
|---|---|
| Raw-only / no calibrated candidate | 2, 3 |
| Cluster key + paired resample | 1, 2 |
| Percentile CI + centered p + contrast RNG | 1 |
| Holm global family + dedupe + non-estimable | 1, 2 |
| Reliability / cal GLM status / flips / bands | 2 |
| Manifest hash + join validation | 2 |
| Eligibility from M08 | 2 |
| Artifacts + CLI + docs | 2, 3 |
| Legacy week-only bootstrap untouched | 1 (new module) |

No TBD placeholders.
