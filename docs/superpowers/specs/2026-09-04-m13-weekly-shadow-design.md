# M13 weekly shadow-mode integration design

Date: 2026-09-04
Status: approved for implementation / implemented on `production/m13-shadow-model`
Roadmap: `docs/modeling_implementation_roadmap.md` § M13
Branch: `production/m13-shadow-model`
Depends on: M12 registry pack `docs/modeling_artifacts/m12/1.0.0/`, weekly
recommend/grade contracts, residual bundle schema `1.0.0`

## Problem

Weekly recommend produces a market baseline card. M12 governs which models may
be production- or shadow-eligible, but nothing yet loads registry tips for an
experimental weekly compare. Without a read-only shadow path, a future ML model
could be wired into `final_card` / submission by accident. Today the only
approved tip is `market_only`; M13 must still ship the plumbing and prove the
future scoring contract without inventing a challenger.

## Goals

1. Add `pick-prophet weekly shadow` that loads only compatible registry tips
   with status `approved` or human-designated `shadow`.
2. Emit a separate experimental artifact pack labelled experimental, including
   market picks/probabilities, optional ML shadow picks/probabilities,
   adjustment/disagreement, warnings, and all model/input hashes.
3. Never mutate `final_card.md`, `submission.json`, production
   `recommendations/`, or any finalized marker.
4. When no compatible **non-baseline** `shadow`/`approved` tip exists, emit
   explicit `status=no_ml_shadow` and market reference output with null ML
   columns (not a silent ML substitute or a second market prediction).
5. Define strict serving adapters for future `residual_logistic` and
   `boosted` registry bundles (feature parity, PIT joins, hash checks).
6. Extend grading to compare market vs shadow vs authorized manual decisions
   when shadow artifacts are present.
7. Fail closed on unsupported model types, missing bundles, schema/protocol
   mismatches, unavailable required features, stale tips, or hash failures.
8. Prove the future scoring path with **in-test synthetic bundles only** — do
   not register stub models or commit synthetic predictions as real candidates.

## Non-goals

- Training residual or boosted models
- Registering a stub / fake ML candidate in the M12 pack
- Silently substituting market probabilities when an ML model is unavailable
- Changing production recommend output or auto-updating final/submitted picks
- Cryptographic key management beyond content hashes
- Reopening M10/M11 promotion decisions

## Approach (choice C)

**Full shadow plumbing + strict serving interfaces for future models.**

- Resolve registry tips from the validated M12 pack (read-only).
- Production market path remains the existing weekly recommend semantics.
- ML shadow path activates only for a tip with `model_type` in
  `{residual_logistic, boosted}`, status in `{approved, shadow}`, compatible
  protocol/matrix schema, validated bundle hash, and available required
  features under PIT rules.
- If no current non-baseline tip exists → `no_ml_shadow` experimental run with
  market reference rows and an explicit reason (e.g. “sole tip is
  market_baseline”). If a current non-baseline tip exists but is incompatible,
  invalid, or unscorable, fail closed rather than disguising it as absence.
- Serving adapters implement a shared interface; boosted may be
  `not_implemented` at the scorer level until a real bundle exists, but the
  interface and fail-closed checks are present. Residual scoring uses the
  existing fixed-offset logistic formula against a hash-checked bundle +
  feature frame built for the slate as-of.

## Registry selection rules

Eligible tips for ML shadow scoring:

- `status ∈ {approved, shadow}`
- `model_type ∈ {residual_logistic, boosted}`
- `protocol_version` and `matrix_schema_version` match the shadow run’s
  declared versions (default `1.0.0`)
- `bundle_path` / `bundle_sha256` present and match on-disk bytes
- Feature set nonempty and ⊆ serving feature frame columns available as-of
- Tip SHA equals current index tip (stale tip → fail closed)
- Referenced approval/shadow attestation, evaluation, promotion policy, approved
  feature set, and lineage all validate under the M12 contract

`market_only` / `market_baseline` is **never** treated as an ML shadow model.
It is the market reference and the production fallback identity.

Selection is deterministic:

- `--model-id` supplied: resolve that exact current tip; missing, retired,
  unsupported, or incompatible selection is an error
- no `--model-id`, zero current non-baseline tips: `no_ml_shadow`
- no `--model-id`, exactly one eligible current non-baseline tip: select it
- no `--model-id`, more than one eligible current non-baseline tip: fail closed
  and require `--model-id`
- no `--model-id`, one or more current non-baseline tips exist but none are
  eligible: error with per-tip rejection reasons, not `no_ml_shadow`

## Serving interface

```text
ShadowScorer.score(slate_rows, *, as_of, feature_frame, registry_entry, bundle)
  -> ShadowScoreResult
```

`ShadowScoreResult` fields (per game / aggregate):

- `model_id`, `model_type`, `entry_sha256`, `bundle_sha256`
- per-game: `p_home` (or pick-side prob), pick, status, warning
- `feature_parity_ok`, missing feature list, timing notes
- never invents probabilities when scoring fails — row status = error / skipped

Rows join by canonical game ID, never by position, display order, or team-name
text. The scorer validates exactly one output per input game, preserves home/away
orientation, rejects duplicate/missing/extra IDs, requires finite probabilities
in `[0, 1]`, and applies a documented deterministic pick rule at `p_home=0.5`.

The registry bundle schema fixes feature names, order, types, categorical levels,
missing-value behavior, preprocessing parameters, model coefficients/structure,
and probability transform. Serving rejects undeclared extra model inputs and
type coercions that would alter training semantics. Do not load arbitrary
pickle/joblib or execute bundle-supplied code. M13 v1 accepts only explicitly
allowlisted, data-only serialization formats and schema versions.

Adapters:

| model_type | Behavior in M13 |
|---|---|
| `market_baseline` | Not an ML scorer; used only as market reference |
| `residual_logistic` | Load/validate allowlisted M08-style JSON bundle; apply fixed-offset logit with declared feature order/preprocessor; require exact feature parity |
| `boosted` | Interface registered; missing real serving implementation or missing bundle → fail closed (no market fill-in) |

Contract tests construct synthetic residual bundles + tiny feature frames in
`tmp_path` only. Those artifacts are never written into
`docs/modeling_artifacts/m12/`.

## Point-in-time input contract

`--as-of` is required, timezone-aware, recorded in UTC, and applied per game.
Every market/feature value must carry source/effective/retrieval timing metadata
required by its schema and must have been available no later than
`min(run_as_of, game_lock_time)`. The feature builder uses the same versioned
matrix semantics declared by the registry entry and emits a hash-checked input
manifest containing source artifacts, schema versions, row/game-ID digest,
feature columns, and timing audit results. A missing or unverifiable timestamp
for a required model input fails the ML path.

The market reference must use one documented canonical market-input schema and
probability conversion identical to weekly recommend (including vig removal,
side/orientation, missing-odds behavior, and tie handling). `--market` may point
to a compatible immutable market artifact; if omitted, the command builds that
same schema from the slate's validated market fields. The manifest records the
market artifact/input hash and odds timestamp. Shadow scoring must not silently
refresh odds or other inputs beyond the declared `--as-of`.

## Shadow run artifacts

Written under a dedicated experimental directory, e.g.
`weekly/<WEEK>/shadow/<run_id>/` or `--output-dir` (must not be the production
recommendations dir or week root that holds `final_card.md` /
`submission.json`).

| File | Role |
|---|---|
| `shadow_manifest.json` | Status (`no_ml_shadow` \| `ml_shadow`), registry tip hashes, input hashes, protocol/schema, label `experimental` |
| `shadow_compare.csv` | Per-game market vs shadow (nullable) picks/probs, disagreement, optional adjustment column (null unless an authorized manual adjustment file is supplied), warnings |
| `shadow_card.md` | Human-readable experimental card clearly labelled non-production |
| `registry_snapshot.json` | Exact validated entry metadata and hashes of its lineage, action/evaluation/policy, feature-set, and bundle references; not a registry mutation |
| `input_manifest.json` | Canonical game-ID digest, source/input hashes, feature schema/order/types, odds timestamps, and PIT audit |

Refuse to write if:

- output path would overwrite `final_card.md`, `submission.json`, or a
  finalized production recommendations tree
- registry `validate` fails
- selected ML tip fails any closed-gate check

The writer resolves and rejects symlink/path traversal into protected production
locations, creates a new run directory exclusively, writes into a staging
directory, fsyncs as appropriate, and atomically publishes only a complete pack.
It never overwrites an existing run. Tests hash protected production artifacts
before and after both successful and failed shadow runs to prove byte-for-byte
immutability. Partial staging output from a failure is not a valid run and is
never auto-detected by grading.

## Grading extension

When `--shadow-dir` (or an unambiguous, complete, manifest-valid experimental
pack is auto-detected) is provided to grade:

- Score market / submitted / manual as today
- Additionally score shadow picks where present
- Verify the shadow manifest, input/game-ID digest, registry snapshot, and all
  referenced artifact hashes before using it
- Join results by canonical game ID and reject duplicates, missing orientation,
  or slate/result identity mismatch
- Emit comparison summary: market vs shadow vs submitted/manual agreement,
  coverage, and pick accuracy; compute log loss/Brier only for sources that
  actually recorded pregame probabilities
- Missing shadow → grade still succeeds with `shadow_status=not_provided`
- `no_ml_shadow` remains explicitly unscored as an ML model; market reference
  rows are not counted a second time as shadow performance
- Never rewrite submission or final card during grade

## CLI

```bash
pick-prophet weekly shadow \
  --slate PATH --as-of TS [--market PATH] \
  [--registry-root docs/modeling_artifacts/m12/1.0.0] \
  [--model-id ID] \
  --output-dir PATH

pick-prophet weekly grade ... [--shadow-dir PATH]
```

`weekly recommend` remains unchanged and production-only.

## Fail-closed matrix

| Condition | Result |
|---|---|
| No current non-baseline tip exists | `no_ml_shadow` + market reference (success; ML columns null) |
| Non-baseline tip exists but none are eligible | error with rejection reasons |
| Unsupported `model_type` selected | error |
| Missing / hash-mismatched bundle | error |
| Protocol or matrix schema mismatch | error |
| Required feature unavailable as-of | error (for ML path) |
| Stale tip / registry invalid | error |
| Attempt to write into final/submission paths | error |
| Boosted selected but scorer unimplemented | error |
| Duplicate/missing/extra game IDs or orientation mismatch | error |
| Required input lacks valid PIT timing metadata | error |
| Probability is nonfinite or outside `[0, 1]` | error |
| Bundle uses executable/unapproved serialization | error |

## Tests (acceptance)

- Registry with only `market_only` → `no_ml_shadow`; market columns filled;
  shadow ML columns null/explicitly absent; experimental label present
- A present but incompatible non-baseline tip errors rather than emitting
  `no_ml_shadow`
- Zero/one/multiple eligible-tip selection follows the deterministic rules;
  `--model-id` resolves only the exact current tip
- Production paths (`final_card`, `submission`, recommend dir) remain
  byte-for-byte unchanged after successful and failed runs
- Synthetic residual bundle in tmp: feature parity pass scores; missing feature
  fails; hash mismatch fails; schema mismatch fails; feature ordering/type and
  unknown-input violations fail
- Pickle/joblib or other executable/unapproved serialization fails before load
- Selecting unsupported / boosted-without-impl fails closed (no market fill-in)
- Stale tip / tampered registry artifact fails
- Duplicate/missing/extra game IDs and home/away orientation mismatch fail
- Post-lock, timezone-naive, missing-timestamp, and source timestamps later than
  the declared as-of cutoff fail PIT validation; no implicit data refresh occurs
- Nonfinite/out-of-range probability output fails
- Existing output run, path traversal, symlink escape, and protected destination
  fail; incomplete staging packs are ignored by grade
- Grade with a valid shadow dir compares three sources; tampered/mismatched pack
  fails; without shadow dir still works; `no_ml_shadow` is not double-counted
- End-to-end on a fixture slate (may use Week 1 slate read-only) producing
  experimental output under an isolated output dir

## Docs / roadmap

- Update M13 status in `docs/modeling_implementation_roadmap.md`
- Add `docs/weekly_shadow.md` operator contract
- Point at M12 registry; do not alter M12 pack contents

## Locked decisions

- Choice **C**: full plumbing + residual/boosted serving interface
- No stub model registration; no synthetic predictions committed as evidence
- `no_ml_shadow` is the expected live outcome until a real ML tip exists
- Shadow is read-only w.r.t. production weekly artifacts
