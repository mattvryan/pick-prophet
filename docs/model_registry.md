# Model registry and promotion gate (M12)

**Status:** implemented (`docs/modeling_artifacts/m12/1.0.0/`)
**Design:** `docs/superpowers/specs/2026-09-04-m12-model-registry-design.md`
**Pack:** append-only, content-addressed registry records + promotion policy

## What is registered in v1

- **One** approved production entry: `market_only` (`model_type=market_baseline`)
- **No** residual or boosted candidate/shadow entries
- Approval is a **bootstrap governance** decision (not evidence the baseline beat
  itself), attested with `approval_kind=bootstrap_baseline`
- M10 / M11 artifact paths + SHA-256 are recorded as provenance for why no ML
  challenger exists

## Lifecycle

`candidate` → `shadow` | `approved` → `retired` (plus genesis rules in the design
spec). Automated evaluation never writes `approved`. Humans approve or designate
shadow only after `eligible_for_human_review`.

## CLI

```bash
pick-prophet registry validate
pick-prophet registry list
pick-prophet registry register-candidate --entry-json PATH
pick-prophet registry evaluate-candidate \
  --candidate-entry-sha256 HASH \
  --package-json PATH \
  --evaluated-at-utc TIMESTAMP
pick-prophet registry approve \
  --model-id ID --evaluation-sha256 HASH --expected-tip HASH \
  --reviewer NAME --rationale TEXT --reviewed-at-utc TIMESTAMP
pick-prophet registry designate-shadow ...  # same attestation flags
pick-prophet registry retire \
  --model-id ID --expected-tip HASH \
  --reviewer NAME --rationale TEXT --reviewed-at-utc TIMESTAMP
```

All mutate commands are non-interactive and require explicit reviewer / rationale
/ tip hashes. Compare-and-swap refuses stale tips.

## Promotion policy

Thresholds live in
`docs/modeling_artifacts/m12/1.0.0/promotion_policy.json` and are referenced by
hash from every evaluation. Changing a threshold requires a new policy version;
old evaluations are not reinterpreted.

## Out of scope

Weekly shadow serving is **M13**. M12 only provides the registry contract and
gate.
