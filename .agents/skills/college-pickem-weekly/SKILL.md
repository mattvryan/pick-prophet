---
name: college-pickem-weekly
description: >-
  Orchestrates the recurring ESPN College Pick'em weekly workflow in pick-prophet:
  slate capture/validation, market and signal refreshes, market-baseline
  recommendation review, final-card preparation, submission recording, pre-lock
  rechecks, and postgame grading. Use for weekly contest operations. Do not use
  for model development, historical research, or general college-football Q&A.
---

# College Pick'em weekly workflow

Agent-neutral operating skill for `pick-prophet` weekly contest work. The
repository CLI and checked-in weekly artifacts are the source of truth. This
skill orchestrates them; it does not reimplement market math, validation,
ingestion, or tiebreaker logic.

Project references:

- `docs/implementation_plan.md`
- `docs/baseline_results.md`
- `docs/early_season_results.md`
- `docs/methodology.md`
- `weekly/README.md`

Detailed procedures: [references/workflow.md](references/workflow.md)
Artifact semantics: [references/output-contract.md](references/output-contract.md)

## Scope

In scope: one contest week under `weekly/YYYY-WNN/`, from slate capture through
grading.

Out of scope: fitting models, multi-season research, inventing CLI commands, or
changing historical point-in-time inputs after the fact.

## Operating modes

Route to the matching section in [references/workflow.md](references/workflow.md):

| Mode | When to use |
|---|---|
| Slate capture and validation | Creating or checking `slate.csv` / `capture_manifest.json` |
| Data refresh | Refreshing immutable market/signal snapshots before lock |
| Recommendation and review | Running baseline recommend + tiebreaker and reviewing signals |
| Final-card preparation | Assembling `final_card.md` / `final_picks.csv` after explicit pick authorization |
| Submission recording | After the user confirms ESPN entry |
| Pre-lock recheck | Re-evaluating after submission without silently mutating the submitted card |
| Postgame grading | After results are final |

When creating or changing weekly files, follow
[references/output-contract.md](references/output-contract.md).

## Essential invariants

- User instructions take precedence over skill guidance.
- Do not produce final picks unless the user explicitly authorizes picks.
- Do not claim selections were entered into ESPN unless the user confirms
  submission or the agent actually performs an authorized submission.
- Preserve point-in-time snapshots and timestamps.
- Never overwrite or silently revise finalized/submitted selections.
- Keep model recommendations distinct from manual overrides.
- Record the evidence and reason for every override.
- Treat betting-market probabilities as the current baseline.
- Treat FPI, SP+, Elo, public percentages, news, injuries, and weather as review
  signals unless historical testing demonstrates independent out-of-sample value.
- Do not use ESPN public-pick percentages to select winners in a standard
  Pick'em contest.
- Do not generate confidence-point rankings for a standard league.
- Handle the designated tiebreaker separately using the consensus market total
  baseline.
- Never expose secrets or print the `CFBD_API_KEY`.
- Use data available before the applicable game lock; prevent hindsight leakage.

## Quick start

1. Identify `weekly/YYYY-WNN/` and inventory existing artifacts.
2. Open [references/workflow.md](references/workflow.md) and run only the
   requested mode.
3. Prefer existing CLI commands; if a needed command is missing, document the gap
   instead of inventing one.
4. Write or update artifacts only as allowed by
   [references/output-contract.md](references/output-contract.md).
