# M01 Evaluation Protocol Implementation Plan

> **For agentic workers:** Execute task-by-task with tests. Steps use checkbox syntax.

**Goal:** Freeze versioned expanding-window evaluation (`protocol_version` 1.0.0) and refactor existing baselines onto that contract.

**Architecture:** Protocol config + fold/pairing helpers + metrics/artifacts; `pick-prophet evaluate` regenerates stamped reports; `analyze` / `analyze-early-season` call the same contracts.

**Tech Stack:** Python 3, pandas/sklearn (existing), pytest, stdlib csv/json.

**Spec:** `docs/superpowers/specs/2026-09-04-m01-evaluation-protocol-design.md`

## Global Constraints

- `protocol_version = "1.0.0"`
- Research seasons `2017–2025`; test seasons `2018–2025`; train `season < S`
- Bootstrap seed `20260904`, `n_boot=500`, week-clustered
- `latest_oot_fold = 2025`; `prospective_holdout = "2026_weekly_shadow"`
- No new models/sources; no production recommend changes
- Paired comparisons require identical `game_id` sets

## File map

| File | Role |
|---|---|
| `src/pick_prophet/evaluation/protocol.py` | Frozen ProtocolConfig + defaults |
| `src/pick_prophet/evaluation/folds.py` | Expanding folds + pair_game_ids |
| `src/pick_prophet/evaluation/metrics.py` | score, calibration, bootstrap deltas |
| `src/pick_prophet/evaluation/artifacts.py` | prediction/summary writers |
| `src/pick_prophet/evaluation/evaluate.py` | End-to-end evaluate runner |
| `src/pick_prophet/evaluation/analyze.py` | Use protocol folds; stamp version |
| `src/pick_prophet/evaluation/early_season.py` | Use protocol; stamp predictions |
| `src/pick_prophet/cli.py` | `evaluate` command |
| `tests/test_protocol.py` | Folds, pairing, leakage, determinism |
| `tests/test_evaluate_metrics.py` | Calibration + bootstrap |
| docs methodology/roadmap/plan | Protocol freeze notes + checkboxes |

### Task 1: Protocol + folds

- [ ] Add `ProtocolConfig` dataclass and `DEFAULT_PROTOCOL`
- [ ] `iter_expanding_folds(seasons) -> list[Fold]` with train_seasons / test_season
- [ ] `pair_game_ids(ids_a, ids_b)` raises on unequal sets
- [ ] Tests: train precedes test; future season mutation does not change earlier fold membership; pairing rejects mismatch
- [ ] Commit

### Task 2: Metrics + artifacts

- [ ] `calibration_bins(y, p, n_bins=10)`
- [ ] `bootstrap_paired_delta(weeks, y, p_a, p_b, metric, n_boot, seed)`
- [ ] `write_predictions` / `write_summary` with required columns
- [ ] Determinism test for bootstrap seed
- [ ] Commit

### Task 3: evaluate CLI + baseline refactor

- [ ] `evaluate(input, output_dir, protocol)` runs walk-forward like analyze, writes stamped summary + predictions
- [ ] Wire `pick-prophet evaluate`
- [ ] Refactor analyze/early_season to use folds + stamp `protocol_version`
- [ ] Existing analysis tests still pass
- [ ] Commit

### Task 4: Docs + PR

- [ ] Update methodology, roadmap M01, implementation plan P2.1
- [ ] Full pytest; open PR from `modeling/m01-evaluation-protocol`
