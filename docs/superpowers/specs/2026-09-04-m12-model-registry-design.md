# M12 model registry and promotion gate design

Date: 2026-09-04
Status: approved for implementation / implemented on `modeling/m12-model-registry`
Roadmap: `docs/modeling_implementation_roadmap.md` § M12
Branch: `modeling/m12-model-registry`
Depends on: M01 protocol `1.0.0`, matrix schema `1.0.0`, M09–M11 close-out
artifacts (esp. M10 `approved_feature_set.json`, M11 `decision.json`)

## Problem

M01–M11 established evaluation standards and recorded that no ML feature set
earned promotion. Without a registry and promotion gate, a future candidate
could be wired into weekly serving by convention rather than by evidence.
M12’s value is the **governance mechanism**, not registering a sophisticated
model.

## Goals

1. Define immutable, schema-versioned registry lifecycle states: `candidate`,
   `shadow`, `approved`, `retired`.
2. For M12 v1, register **one** immutable `market_only` baseline entry with
   status `approved`, plus provenance linking the M11 no-challenger decision.
3. Register **no** residual or boosted candidate/shadow entries in v1.
4. Record explicitly that market baseline approval is a **bootstrap governance
   decision**, not evidence that the baseline beat itself.
5. Implement a generic promotion evaluator for **future** candidates with the
   gates listed below; automated gates may emit `eligible_for_human_review`
   only and must **never** set `approved`.
6. Provide CLI commands to validate, list, evaluate, approve, and retire.
7. Fail closed on missing evidence, hash/schema mismatches, unequal paired IDs,
   ineligible features, unresolved leakage, empty non-baseline feature sets,
   and approval claims without a valid human approval record.
8. Keep weekly serving integration out of M12 (M13).

## Non-goals

- Weekly shadow/serving integration (M13)
- Training boosted or residual models
- Registering rejected M08 variants as candidates or shadow models
- Cryptographic key management / PKI signatures (content-addressed SHA-256 +
  reviewer attestation fields are sufficient for v1 but do not authenticate
  reviewer identity)
- Mutating existing registry records in place
- Reinterpreting `review_only` as promoted

## Approach

**Append-only, content-addressed registry.** Each logical model has a stable
`model_id`. Every state change writes a new hashed record that references the
prior record hash. Human actions are **attested**, not cryptographically signed:
canonical JSON is protected by SHA-256 and contains explicit `reviewer` /
`reviewed_at_utc` / `rationale` fields. These fields provide attribution and an
audit trail but do not authenticate reviewer identity. No private keys in v1.

**Bootstrap approved baseline.** Create `market_only` / `model_type:
market_baseline` as the sole `approved` production entry. It has no fitted
bundle. Approval rationale documents bootstrap governance and cites M10/M11
artifacts (paths + SHA-256).

**Generic evaluator for future non-baseline candidates.** Evaluation consumes a
candidate package (bundle + metrics + coverage + feature list + M10 reference)
and emits an immutable evaluation record. Pass → `eligible_for_human_review`.
Fail → terminal evaluation status that cannot be approved without a new
evaluation. Human `approve` requires a prior passing evaluation record hash.

## Lifecycle states

| State | Meaning | Who can create |
|---|---|---|
| `candidate` | Registered for evaluation; not servable | Operator / tooling |
| `shadow` | Eligible for non-mutating weekly shadow (M13) after human designation | Human only, after gates |
| `approved` | Production-eligible reference model | Human only, after gates |
| `retired` | Superseded or withdrawn; retained for audit | Human only |

v1 registers only the approved market baseline. Shadow transitions for ML
candidates are implemented and tested but unused until a candidate exists.

Permitted transition graph:

- genesis → `candidate` for a non-baseline model registration
- `candidate` → `shadow` after a passing evaluation and human designation
- `candidate` → `approved` after a passing evaluation and human approval
- `shadow` → `approved` after a passing evaluation and human approval
- `candidate` / `shadow` / `approved` → `retired` by human action

All other transitions fail closed. In particular, `retired` is terminal;
approval cannot be automated; and a new model version must use a new genesis
`candidate` rather than resurrecting or rewriting a retired lineage.

State transitions never rewrite prior rows. A transition record includes:
`prior_record_sha256`, `model_id`, `from_status`, `to_status`, hashes of
supporting artifacts, reviewer, timestamp, rationale.

## Immutable artifact schemas (v1)

Tracked under `docs/modeling_artifacts/m12/1.0.0/` (compact; no bulk
predictions). Suggested files:

| Artifact | Role |
|---|---|
| `registry_index.json` | Manifest of current tip hashes per `model_id` + schema versions |
| `entries/*.json` | Immutable registry entry records (content-addressed) |
| `evaluations/*.json` | Immutable promotion evaluation records |
| `approvals/*.json` | Human approval records |
| `retirements/*.json` | Retirement / supersession records |
| `promotion_policy.json` | Versioned, immutable gate definitions and exact thresholds |
| `manifest.json` | SHA-256 of every other committed artifact in the pack; excludes itself |

Content-addressed filenames use `<record_sha256>.json`. Paths stored in registry
records are normalized POSIX paths relative to the repository root. Validation
rejects absolute paths, `..` traversal, paths outside configured approved roots,
and symlinks that resolve outside those roots. Referenced large/private evidence
may live outside the compact M12 pack but must be under an approved evidence root
and must be identified by normalized path plus SHA-256.

### Registry entry (required fields)

- `artifact_schema_version`, `registry_version`, `record_sha256`
- `model_id` (stable), `model_version`, `model_type`
  (`market_baseline` | `residual_logistic` | `boosted` | …)
- `status`
- `prior_record_sha256` (nullable for genesis)
- `protocol_version`, `matrix_schema_version`
- `feature_set` (list; empty allowed only for `market_baseline`)
- `m10_approved_feature_set_path` / `_sha256` (required when features nonempty)
- `m11_decision_path` / `_sha256` (required for v1 baseline provenance)
- `bundle_path` / `bundle_sha256` (required for non-baseline; **forbidden /
  null** for `market_baseline`)
- `probability_source`, `timing_limitations`
- `evaluation_coverage`, `limitations`
- `serving_requirements`, `fallback_behavior`
- `metrics_summary` (optional for baseline bootstrap)
- For approved records: `approval_record_sha256`; inline approval fields are not
  permitted

**Canonical hash rule:** serialize the record as JSON with sorted keys and
compact separators; compute SHA-256 over UTF-8 bytes of that object **with the
`record_sha256` field omitted**; then set `record_sha256` to that digest.
Validators recompute the same way and reject mismatch.

### Approved `market_only` entry content

- `model_id`: e.g. `market_only`
- `model_type`: `market_baseline`
- `status`: `approved`
- No fitted-model bundle
- Probability source and timing limitations (vig-removed moneyline /
  implied-prob semantics; pre-lock availability constraints)
- Protocol `1.0.0` and compatible matrix schema `1.0.0`
- M10 and M11 decision paths + SHA-256
- Evaluation coverage / limitations (incl. M10 inference window 2022–2025 for
  feature evidence; baseline itself is market-derived)
- Serving requirements and fallback behavior (baseline *is* the fallback)
- A referenced bootstrap approval record containing reviewer, approval
  timestamp, and rationale stating **bootstrap governance**, not “beat itself”
- Provenance: M11 `status=not_run_no_promoted_features` explains why no ML
  candidate is registered

The baseline is the sole approved-genesis exception. Validation permits an
approved genesis entry without an evaluation only when all of the following are
true: `model_type=market_baseline`, `model_id=market_only`, the referenced
approval record has `approval_kind=bootstrap_baseline`, and its provenance
references and hashes validate. Every other `approved` or `shadow` transition
requires a passing promotion evaluation.

### Promotion evaluation record

Automated gates only. Outcome ∈
`{failed, eligible_for_human_review}`. Never `approved`.

Required checks (all must pass for `eligible_for_human_review`):

1. Exact protocol and matrix-schema compatibility with the comparison baseline
   and declared schemas.
2. Immutable artifact and input hashes match on-disk bytes.
3. Identical paired held-out game IDs vs baseline.
4. Held-out log-loss improvement (candidate better than baseline on the paired
   set; direction fixed in protocol / evaluator constants).
5. Held-out Brier improvement (same).
6. No material calibration regression under the exact threshold in the
   referenced promotion policy.
7. Season-consistency requirement in the referenced promotion policy passes.
8. Coverage and pre-lock availability requirements in the referenced promotion
   policy pass.
9. No unresolved leakage finding.
10. Candidate features ⊆ M10 `promoted_features` for the referenced approved
    feature-set artifact (hash-validated). `review_only`, `rejected`,
    `unavailable`, and unknown features fail closed.
11. Non-baseline models require a fitted bundle and nonempty promoted feature
    set.

Missing required evidence → `failed` (fail closed).

Each evaluation record must contain:

- evaluation artifact schema version, record hash, evaluator implementation
  version, and evaluation timestamp
- candidate entry hash and comparison-baseline entry hash
- promotion-policy path and SHA-256
- prediction/evidence artifact paths and SHA-256 values for candidate and
  baseline
- paired held-out game-ID-set digest, game count, season list, and per-season
  counts
- aggregate paired log loss and Brier score, paired deltas, uncertainty output,
  and per-season metrics
- calibration metrics and regression amount
- coverage statistics and pre-lock timing classification
- leakage status and evidence reference
- approved-feature-set path/hash and normalized candidate feature list
- one explicit pass/fail result and reason per gate
- final outcome (`failed` or `eligible_for_human_review`)

Bulk predictions are not committed to the compact registry pack. Their immutable
locations and hashes are recorded, and the paired ID digest/count commits the
exact comparison population.

### Promotion policy

`promotion_policy.json` is immutable, schema-versioned, content-hashed, and
referenced by every evaluation. It must predeclare before candidate evaluation:

- metric directions and exact aggregate improvement thresholds for log loss and
  Brier score
- uncertainty method and any interval/significance criterion
- exact calibration metric(s) and maximum permitted regression
- minimum paired game count, minimum test-season count, and minimum per-season
  sample size
- the precise season-consistency rule (including how many seasons must improve
  and whether the rule applies separately to both scoring metrics)
- minimum feature/prediction coverage and the definition of eligible coverage
- allowed timing classifications and the exact pre-lock availability rule
- leakage statuses that fail closed

Thresholds may not be implicit constants in evaluator code. Changing a threshold
requires a new policy version and hash; an existing evaluation is never
reinterpreted under a later policy.

### Human approval record

- References evaluation record SHA-256 with outcome
  `eligible_for_human_review`
- `reviewer`, `reviewed_at_utc`, `rationale`
- Target `model_id` / intended `to_status` (`approved` or optionally `shadow`
  in later use)
- Content hash of the approval record itself
- `approval_kind` (`bootstrap_baseline` | `candidate_promotion` |
  `shadow_designation`)

Except for the narrowly defined bootstrap-baseline exception, `registry approve`
and `registry designate-shadow` refuse unless the referenced evaluation is
present, untampered, eligible, and evaluates the current lineage tip.

### Retirement / supersession record

- References prior approved (or shadow) record hash
- `reviewer`, timestamp, rationale
- Optional `superseded_by_model_id` / record hash
- Writes new tip status `retired` without mutating the prior approved bytes

Retirement writes two immutable records: a retirement action record and a new
registry entry whose `status=retired`, whose `prior_record_sha256` is the current
tip, and whose supporting-artifact list includes the retirement record hash.

## Fail-closed rules

Reject / refuse when:

- Required evidence is missing
- Any referenced hash mismatches on-disk content
- Protocol or matrix schemas are incompatible
- Paired held-out game ID sets differ
- Candidate includes `review_only`, `rejected`, `unavailable`, or unknown
  features
- Any leakage finding is unresolved
- Feature set is empty for a non-baseline model
- A candidate or entry claims `approved` without a valid human approval record
- Non-baseline lacks a fitted bundle
- Automated path attempts to write `status=approved`
- A requested transition is not in the permitted transition graph
- An evaluation or approval targets a stale lineage tip
- A path is absolute, traverses outside an approved root, or escapes through a
  symlink
- A lineage contains a cycle, missing ancestor, orphaned action record, duplicate
  model version, unsupported schema/status, or inconsistent transition metadata

Registry mutations use exclusive creation for immutable records and atomic
replacement for `registry_index.json` and `manifest.json`. Mutating commands
require an expected current tip and perform compare-and-swap immediately before
commit; a stale tip fails without writing a new index. The manifest excludes
itself from its digest map. `validate` recomputes every record and artifact hash,
walks every lineage, validates action-record reachability, and verifies index and
manifest consistency. `list` validates first and refuses to report an invalid
registry as healthy.

## CLI (non-interactive)

Under `pick-prophet registry …`:

| Command | Behavior |
|---|---|
| `validate` | Verify index, tip hashes, on-disk artifact digests, schema versions |
| `list` | Print model_id, status, tip hash, model_type |
| `register-candidate` | Exclusively write a genesis candidate entry; never servable |
| `evaluate-candidate` | Run gates; write evaluation record; never approve |
| `approve` | Require `--reviewer`, `--rationale`, evaluation hash; write approval + new entry tip |
| `designate-shadow` | Require `--reviewer`, `--rationale`, evaluation hash; write attestation + shadow tip |
| `retire` | Require `--reviewer`, `--rationale`, target model/tip; write retirement record |

No interactive prompts. Paths and hashes are explicit flags or config.

## Tests (acceptance)

- Baseline entry validates without a fitted bundle
- Non-baseline models require a bundle and nonempty promoted feature set
- Failed gates cannot produce approval
- Passing automated gates produce only `eligible_for_human_review`
- Human approval is required for `approved`
- Tampering with any referenced artifact is detected
- `review_only` / rejected / unavailable / unknown features are rejected
- Unequal paired IDs fail
- Prior registry records remain immutable (rewrite attempt / tip swap detected)
- Retaining `market_only` with no challenger is a valid successful outcome
- Exact bootstrap-baseline exception validates; all broader evaluation-free
  approval attempts fail
- Invalid transition edges and resurrection of retired lineages fail
- Cycles, missing ancestors, orphan approvals/retirements, duplicate model
  IDs/versions, and stale-tip concurrent updates fail
- Duplicate normalized feature names fail
- Absolute paths, path traversal, and symlink escape fail
- Unknown lifecycle states and unsupported schema versions fail
- `manifest.json` is excluded from its own digest map while all other committed
  pack artifacts are covered
- A synthetic fully passing candidate produces only
  `eligible_for_human_review`, never `approved`

## Docs / roadmap

- Update M12 status in `docs/modeling_implementation_roadmap.md`
- Add `docs/model_registry.md` (operator-facing contract)
- Point at M10/M11 artifacts; do not reopen M11 training

## Out of scope handoff to M13

M13 loads only compatible **approved** (and optionally human-designated
**shadow**) registry tips for weekly experimental output, without mutating the
market card. M12 only supplies the registry contract and gate.

## Open decisions locked by this brief

- Approach **A**: full registry + evaluator now
- v1 registered set: approved `market_only` only; no M08/M11 ML candidates
- Human action = content-addressed SHA-256 + reviewer attestation fields; this is
  not cryptographic identity signing (no crypto KM)
- Artifact root: `docs/modeling_artifacts/m12/1.0.0/`
