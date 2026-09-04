# M08 Market-Residual Logistic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fit fixed-offset market-residual logistics for five predeclared variants on matrix schema 1.0.0, with fold-nested preprocess, custom L-BFGS-B objective, and protocol-compatible prediction artifacts.

**Architecture:** Variant column registries → fold-local preprocessor → `FixedOffsetLogit` (SciPy L-BFGS-B on mean NLL + λ/2‖β‖²) → walk-forward runner writing protocol predictions, residual details, JSON model bundles, eligibility + summary + manifest.

**Tech Stack:** Python 3.11+, NumPy (via SciPy/sklearn stack), **SciPy as direct dependency**, existing evaluation protocol/folds/metrics/artifacts, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-m08-market-residual-design.md`

## Global Constraints

- `logit(P) = home_market_logit + Xβ`; **no intercept**; market logit never in `X` or as fitted coeff
- Raw moneylines prohibited from `X`; `neutral_site` absent (complement of `home_field_advantage`)
- Objective: mean `logaddexp(0, o+Xβ) − y(o+Xβ)` + `(λ/2)‖β‖²` with `λ=1.0`, `β₀=0`, L-BFGS-B, `max_iter=1000`; convergence failure = hard fold error
- SciPy is a **direct** `pyproject.toml` dependency
- Protocol `p_home` = raw `σ(o+adj)`; clipping only in residual-detail `p_home_scored`
- Canonical eligibility shared across all variants per fold; unequal emitted IDs fail
- Preprocess train-only; missing indicators always present; drop-one categorical reference; reject constant-span encodings
- Fixed hyperparameters; no HP search / feature selection
- Model bundles = canonical JSON only (no pickle); hash exact bytes
- Matrix schema 1.0.0 + protocol 1.0.0 stamped everywhere

## File map

| File | Role |
|---|---|
| `pyproject.toml` | Add `scipy` dependency |
| `src/pick_prophet/models/residual_variants.py` | Frozen variant column tuples + gates |
| `src/pick_prophet/models/residual_preprocess.py` | Fold-local numeric/categorical transform |
| `src/pick_prophet/models/fixed_offset_logit.py` | Objective, gradient, L-BFGS-B fit/predict |
| `src/pick_prophet/models/residual_fit.py` | Walk-forward orchestration + artifacts |
| `src/pick_prophet/models/residual_bundle.py` | Canonical JSON serialize/validate/hash |
| `src/pick_prophet/cli.py` | `fit-residual` |
| `tests/test_residual_*.py` | Unit + integration tests |
| `docs/market_residual_model.md` | Model card |
| roadmap / matrix_schema pointer | Status updates |

---

### Task 1: SciPy dep + variants registry

**Files:** `pyproject.toml`, `src/pick_prophet/models/__init__.py`, `residual_variants.py`, `tests/test_residual_variants.py`

**Interfaces:**
- `VARIANTS: dict[str, tuple[str, ...]]` with exact columns from spec
- `assert_variant_columns_allowed()` ⊆ `MODEL_FEATURE_COLUMNS`
- Forbidden: baseline cols, moneylines, `neutral_site`, audit/target/id/ratings

- [ ] Add `scipy>=1.11,<2` (or current compatible pin) to dependencies; install in venv
- [ ] TDD variant membership + prohibition tests
- [ ] Commit

---

### Task 2: Fixed-offset estimator

**Files:** `fixed_offset_logit.py`, `tests/test_fixed_offset_logit.py`

**Interfaces:**
- `sigmoid(z)`, `objective(beta, X, y, o, lam)`, `gradient(...)`
- `fit_fixed_offset_logit(X, y, offset, *, lam=1.0, max_iter=1000, ftol=..., gtol=...) -> FitResult`
- `predict_raw(offset, X, beta) -> p_raw`
- `FitResult`: beta, success, nit, fun, message; raise on `not success`

- [ ] Tiny fixture: objective/grad match finite differences / hand calc
- [ ] `beta=0` ⇒ `p == sigmoid(offset)`
- [ ] Forced non-convergence path raises
- [ ] Commit

---

### Task 3: Fold preprocessor

**Files:** `residual_preprocess.py`, `tests/test_residual_preprocess.py`

**Interfaces:**
- `NUMERIC_COLUMNS` / `CATEGORICAL_COLUMNS` maps from variant columns
- `FoldPreprocessor.fit(rows, columns) -> self`
- `transform(rows) -> (X: np.ndarray, feature_names: list[str])`
- State: medians, means, scales, cat vocab + reference level, feature order

Rules from spec: always missing indicators; all-missing → fill 0 scale 1 ind 1; unknown sentinel; drop lex-first non-unknown reference; reject constant-span.

- [ ] Tests: train-only fit (mutate test stats unused), unseen → unknown, all-missing stable schema, no implicit intercept from full one-hot
- [ ] Commit

---

### Task 4: Bundles + walk-forward + CLI

**Files:** `residual_bundle.py`, `residual_fit.py`, `cli.py`, `tests/test_residual_fit.py`

**Interfaces:**
- `eligibility_mask(frame) -> mask, exclusions`
- `validate_baseline_consistency(frame, tol=...) -> None` hard error
- `fit_residual_walkforward(matrix_path, protocol, output_dir) -> summary`
- Writes: protocol predictions, residual details, per fold×variant JSON bundles, eligibility report, summary, run manifest
- All variants share canonical test IDs per fold or fail

- [ ] Integration on synthetic matrix covering 2–3 seasons
- [ ] Tests for moneyline ban, baseline consistency, ID equality, serialize round-trip, determinism, prohibited columns
- [ ] CLI `fit-residual`
- [ ] Commit

---

### Task 5: Docs + roadmap + PR

- [ ] `docs/market_residual_model.md` model card
- [ ] Roadmap M08 implemented; matrix_schema pointer
- [ ] Full pytest + ruff; open PR

---

## Self-review vs spec

Custom objective/SciPy, variant column diffs (no neutral/moneylines), raw vs scored p, shared eligibility, drop-one encoding, JSON bundles, baseline consistency — all tasked. No TBD placeholders.
