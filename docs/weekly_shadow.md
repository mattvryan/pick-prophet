# Weekly shadow mode (M13)

**Status:** implemented
**Design:** `docs/superpowers/specs/2026-09-04-m13-weekly-shadow-design.md`
**Registry:** `docs/modeling_artifacts/m12/1.0.0/` (read-only)

## Behavior

`pick-prophet weekly shadow` writes an **experimental** pack under `--output-dir`.
It never mutates `final_card.md`, `submission.json`, or production
`recommendations/`.

With today’s registry (sole tip `market_only`), the run status is
`no_ml_shadow`: market reference rows are filled; ML shadow columns are empty.

If a non-baseline tip exists but is incompatible, the command **errors** (does
not pretend the model is absent).

## CLI

```bash
pick-prophet weekly shadow \
  --slate weekly/2026-W01/slate.csv \
  --as-of 2026-08-28T12:00:00Z \
  --output-dir /tmp/pp-shadow-run

pick-prophet weekly grade \
  --week-dir weekly/2026-W01 \
  --results PATH \
  --shadow-dir /tmp/pp-shadow-run
```

Optional `--feature-frame-json` and `--model-id` are required for a future
`ml_shadow` path once a residual/boosted tip is registered.

## Serving

- `residual_logistic`: allowlisted JSON bundles only; fixed-offset logit; exact
  feature parity; fail closed on hash/schema/feature/ID issues.
- `boosted`: interface present; scoring not implemented → fail closed (no market
  fill-in).
- Pickle/joblib and other executable formats are rejected before load.
