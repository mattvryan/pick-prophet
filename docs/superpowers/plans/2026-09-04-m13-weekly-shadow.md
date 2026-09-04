# M13 Weekly Shadow Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship read-only weekly shadow runs that load M12 registry tips, emit experimental compare packs (`no_ml_shadow` today), and prove residual/boosted serving contracts with in-test synthetic bundles only.

**Architecture:** `weekly/shadow_select.py` (tip selection) → `weekly/shadow_serving.py` (scorers) → `weekly/shadow.py` (run + atomic writer) → grade extension + CLI. Production recommend/final/submission untouched.

**Tech Stack:** Existing weekly recommend/validate, M12 `RegistryStore`, M08 `load_bundle` + fixed-offset sigmoid, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-m13-weekly-shadow-design.md`

## Global Constraints

- Never mutate `final_card.md`, `submission.json`, production recommendations, or M12 pack
- `no_ml_shadow` only when zero current non-baseline tips; incompatible present tips → error
- Fail closed: hashes, schemas, features, stale tips, bad IDs, PIT, unapproved serialization
- Synthetic bundles only in tests; no stub registry registration
- Atomic exclusive run dirs; incomplete staging ignored by grade

## File map

| Path | Role |
|---|---|
| `src/pick_prophet/weekly/shadow_select.py` | Eligible tip discovery / selection rules |
| `src/pick_prophet/weekly/shadow_serving.py` | Scorer protocol; residual JSON; boosted not_implemented |
| `src/pick_prophet/weekly/shadow.py` | Run shadow; market ref; write pack; path guards |
| `src/pick_prophet/weekly/grade.py` | Optional `--shadow-dir` compare |
| `src/pick_prophet/cli.py` | `weekly shadow`; grade `--shadow-dir` |
| `docs/weekly_shadow.md` | Operator contract |
| `docs/modeling_implementation_roadmap.md` | M13 status |
| `tests/test_m13_weekly_shadow.py` | Acceptance tests |

---

### Task 1: Selection + serving contracts

- [ ] Implement select + residual/boosted scorers with fail-closed matrix
- [ ] Tests: synthetic residual pass/fail; boosted fails; pickle rejected
- [ ] Commit

### Task 2: Shadow runner + writer + CLI

- [ ] `run_weekly_shadow`; `no_ml_shadow` path; atomic write; protected paths
- [ ] E2E Week1 slate isolated outdir; immutability hashes
- [ ] Commit

### Task 3: Grade extension + docs + PR

- [ ] Grade shadow compare; docs; roadmap; PR

---

## Self-review

Selection rules, serving interface, no_ml_shadow vs error distinction, atomic writer, grade, tests — tasked.
