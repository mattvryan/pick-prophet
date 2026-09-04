# M12 Model Registry and Promotion Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an append-only, content-addressed model registry with a fail-closed promotion evaluator, bootstrap-approved `market_only`, and CLI mutate/validate commands — no weekly serving.

**Architecture:** `pick_prophet.registry` package owns hashing, path safety, immutable records, index CAS, evaluator (policy-driven), and transitions. Compact pack lives under `docs/modeling_artifacts/m12/1.0.0/`. Automated gates emit only `eligible_for_human_review`.

**Tech Stack:** Python stdlib + pytest; reuse `approved_feature_set` / M11 decision hash validation patterns.

**Spec:** `docs/superpowers/specs/2026-09-04-m12-model-registry-design.md`

## Global Constraints

- Lifecycle: `candidate` | `shadow` | `approved` | `retired`; only permitted edges
- v1 pack: sole `approved` entry = `market_only` / `market_baseline`; no M08/boosted candidates
- Baseline approval = bootstrap governance via `approval_kind=bootstrap_baseline`, not “beat itself”
- Automated evaluator never writes `approved`; human approval/shadow require eligible evaluation (except bootstrap)
- Content-addressed SHA-256 (hash with `record_sha256` omitted); reviewer attestation ≠ crypto identity
- Paths: repo-relative POSIX; reject absolute/`..`/symlink escape; approved roots only
- Index/manifest CAS; exclusive create for immutable records; manifest excludes itself
- No weekly serving (M13); no boosting deps; no residual candidate registration

## File map

| Path | Role |
|---|---|
| `src/pick_prophet/registry/__init__.py` | Public exports |
| `src/pick_prophet/registry/hashing.py` | Canonical JSON + record SHA-256 |
| `src/pick_prophet/registry/paths.py` | Normalize/validate paths under approved roots |
| `src/pick_prophet/registry/policy.py` | Load/validate `promotion_policy.json` |
| `src/pick_prophet/registry/records.py` | Build/validate entry, evaluation, approval, retirement |
| `src/pick_prophet/registry/store.py` | Index, exclusive write, CAS tip, validate, list |
| `src/pick_prophet/registry/evaluate.py` | Gate runner → evaluation record |
| `src/pick_prophet/registry/transitions.py` | register / approve / shadow / retire |
| `src/pick_prophet/registry/bootstrap.py` | Materialize v1 pack with market_only |
| `src/pick_prophet/cli.py` | `registry` subcommands |
| `docs/modeling_artifacts/m12/1.0.0/**` | Committed pack |
| `docs/model_registry.md` | Operator contract |
| `docs/modeling_implementation_roadmap.md` | M12 status |
| `tests/test_m12_registry_*.py` | Acceptance tests |

---

### Task 1: Hashing, paths, policy, record builders

**Files:** `registry/hashing.py`, `paths.py`, `policy.py`, `records.py`, `tests/test_m12_registry_hashing.py`

**Interfaces:**
```python
def canonical_dumps(obj: dict) -> str
def sha256_bytes(data: bytes) -> str
def sha256_file(path: Path) -> str
def record_sha256(payload: dict) -> str  # omit record_sha256 field
def attach_record_sha256(payload: dict) -> dict

def normalize_repo_path(path: str | Path, *, repo_root: Path, allowed_roots: Sequence[str]) -> str
def resolve_safe(path: str, *, repo_root: Path, allowed_roots: Sequence[str]) -> Path

def load_promotion_policy(path: Path, *, expected_sha256: str | None = None) -> dict

def build_registry_entry(**fields) -> dict
def build_approval_record(**fields) -> dict
def build_evaluation_record(**fields) -> dict
def build_retirement_record(**fields) -> dict
def validate_entry_shape(entry: dict) -> None
```

- [ ] TDD hash omit-self, path traversal reject, policy required keys
- [ ] Implement
- [ ] Commit

---

### Task 2: Store validate/list + CAS + bootstrap market_only pack

**Files:** `store.py`, `bootstrap.py`, `docs/modeling_artifacts/m12/1.0.0/**`, `tests/test_m12_registry_store.py`

**Interfaces:**
```python
@dataclass
class RegistryStore:
    root: Path  # docs/modeling_artifacts/m12/1.0.0
    repo_root: Path

    def validate(self) -> None
    def list_models(self) -> list[dict]
    def write_record(self, kind: str, payload: dict) -> dict  # exclusive
    def cas_set_tip(self, model_id: str, *, expected_tip: str | None, new_tip: str) -> None
    def tip(self, model_id: str) -> str | None

def bootstrap_m12_v1(*, repo_root: Path, reviewer: str, reviewed_at_utc: str) -> Path
```

Bootstrap creates policy, bootstrap approval, approved `market_only` entry (no bundle), index tip, manifest (excludes self). Hash-check M10/M11 artifacts.

- [ ] Tests: baseline validates without bundle; no challenger = success; manifest excludes self; tip CAS stale fails
- [ ] Implement + materialize pack
- [ ] Commit

---

### Task 3: Evaluator + transitions (fail-closed)

**Files:** `evaluate.py`, `transitions.py`, `tests/test_m12_registry_evaluate.py`, `tests/test_m12_registry_transitions.py`

**Interfaces:**
```python
def evaluate_candidate(store, *, candidate_entry_sha256: str, package: CandidatePackage, policy_path: str) -> dict
# returns evaluation record; outcome failed | eligible_for_human_review

def register_candidate(store, entry_fields, *, expected_absent: bool = True) -> dict
def approve(store, *, model_id, evaluation_sha256, reviewer, rationale, reviewed_at_utc, expected_tip) -> dict
def designate_shadow(store, *, model_id, evaluation_sha256, reviewer, rationale, reviewed_at_utc, expected_tip) -> dict
def retire(store, *, model_id, reviewer, rationale, reviewed_at_utc, expected_tip, superseded_by=None) -> dict
```

Gates per spec + policy thresholds. Feature eligibility via M10 promoted set. Bootstrap exception only for market_only.

- [ ] Tests covering all acceptance bullets in spec
- [ ] Implement
- [ ] Commit

---

### Task 4: CLI + docs + roadmap + PR

**Files:** `cli.py`, `docs/model_registry.md`, roadmap, spec status → approved/implemented

Commands: `validate`, `list`, `register-candidate`, `evaluate-candidate`, `approve`, `designate-shadow`, `retire`.

- [ ] Wire CLI; docs; roadmap M12 complete
- [ ] Full pytest; PR

---

## Self-review vs spec

Bootstrap exception, transition graph, policy-driven thresholds, CAS/immutability, path safety, feature gates, human-only approve/shadow, CLI surface, tests list — tasked. No weekly serving. No TBD.
