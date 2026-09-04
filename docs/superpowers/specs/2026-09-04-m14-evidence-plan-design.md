# M14 evidence-gap analysis and research protocol 2.0 design

Date: 2026-09-04
Status: implemented
Branch: `codex/m14-evidence-plan`

## Decision

M14 freezes the next research cycle before M15–M19 source results are known. It
does not fit a model. Historical 2022–2025 outcomes remain usable for
predeclared walk-forward comparisons, but are not described as a pristine final
holdout. The 2026 weekly stream is prospective and locked away from development.

## Inputs and diagnosis

The analysis consumes only committed M10 compact evidence, the M05 inventory,
and the M06 feasibility memo. M10 contains 3,195 paired games in 66 week
clusters across 2022–2025. Every tested family-level log-loss interval crossed
zero. No historical ESPN Pick'em slate archive has been verified, market
opening/movement fields were unavailable, and rating publication timing remains
unresolved.

## Outputs

- `docs/research_protocol_2.md`: human-readable frozen rules
- `docs/experiment_ledger_2.json`: machine-readable hypotheses and eligibility
- `docs/modeling_artifacts/m14/2.0.0/`: deterministic evidence gaps, approximate
  power/MDE table, summary, and content hashes
- `src/pick_prophet/evaluation/protocol.py`: registered protocol `2.0.0`

The MDE calculation backs an approximate standard error out of the existing
week-cluster bootstrap interval and reports the two-sided 80% detectable effect.
Square-root scaling to 6,000 games is illustrative only; it is not a substitute
for clustered simulation and cannot promote a source.

## Source-family order

1. Verified ESPN sampling frame (target-population validity)
2. Timestamped market depth (baseline validity)
3. PIT ratings (plausible market disagreement)
4. Chronological team efficiency (better on-field measurement)
5. Dated personnel/program context (early-season priors)

Feasibility, timing, licensing, and coverage gates precede modeling. Collection
effort does not entitle a source to enter M20.

## Acceptance

- Rebuild is deterministic and source hashes are verified.
- Protocol 2.0 excludes 2026 from all historical folds.
- The ledger contains no outcome-dependent dispositions.
- Exact promotion rules are frozen before later source evaluation.
- Unknown M10 status or inference window fails closed.
