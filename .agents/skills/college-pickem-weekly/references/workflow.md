# Weekly Pick'em workflow

Operational procedure for agents. Use repository CLI commands exactly as shown.
Do not reimplement validation, odds, ratings, or tiebreaker math in the skill.

Supporting research context (not weekly steps):

- `docs/baseline_results.md`
- `docs/early_season_results.md`
- `docs/implementation_plan.md`

Artifact rules: [output-contract.md](output-contract.md)

## 0. Discover week state

1. Locate or create `weekly/YYYY-WNN/` (example: `weekly/2026-W01/`).
2. Inventory present files: `slate.csv`, `capture_manifest.json`, `context.md`,
   `market/`, `signals/`, recommendation dirs, `tiebreaker/`, `final_card.md`,
   `final_picks.csv`, any submission/results artifacts.
3. Ask which mode to run if the user did not specify one.
4. Do not generate final picks unless the user explicitly authorizes picks.

## 1. Slate capture and validation

### Capture / confirm

Record the ESPN contest slate into `slate.csv` and provenance into
`capture_manifest.json`. Required fields include at least:

- `display_order`
- teams (`away_team`, `home_team`)
- `neutral_site`
- lock times (`lock_at_utc`, displayed lock text, timezone assumption)
- public-pick percentages
- CFBD game IDs when matched
- capture timestamp and source

Identify the designated tiebreaker game (contest UI / user confirmation). Store
that identity in context notes if no dedicated slate column exists yet.

### Validate

```bash
pick-prophet weekly validate-slate weekly/YYYY-WNN/slate.csv
```

Optional lock check for a planned recommendation time:

```bash
pick-prophet weekly validate-slate weekly/YYYY-WNN/slate.csv \
  --as-of 2026-09-05T16:00:00Z
```

Exit nonzero means fix errors before continuing. Warnings (for example missing
`espn_game_id`) may proceed when acknowledged.

## 2. Data refresh

### Signals (supported CLI)

```bash
pick-prophet weekly fetch-signals --slate weekly/YYYY-WNN/slate.csv
```

Optional fixed stamp:

```bash
pick-prophet weekly fetch-signals \
  --slate weekly/YYYY-WNN/slate.csv \
  --snapshot 20260904T151044Z
```

Writes an immutable directory under `weekly/YYYY-WNN/signals/<snapshot>/`.

### Market snapshot (capability gap)

There is **no** committed `pick-prophet weekly fetch-market` command today.
Week directories may already contain immutable market snapshots such as:

`weekly/YYYY-WNN/market/<snapshot>/market.csv`
`weekly/YYYY-WNN/market/<snapshot>/manifest.json`

Until a CLI exists:

1. Prefer the latest existing `market.csv` whose `snapshot_at_utc` precedes the
   relevant locks.
2. If a new market pull is required, obtain it through an explicitly authorized
   repository process or manual import; do not invent a CLI subcommand.
3. Never overwrite an existing snapshot directory.

### Timing check

Confirm each used snapshot timestamp precedes the lock times for games still
open. Reject post-lock data for those games.

## 3. Recommendation and review

### Market-baseline recommendations

Use the latest market snapshot path when available (do not rely on screenshot
moneylines once a CFBD/market snapshot exists):

```bash
pick-prophet weekly recommend \
  --slate weekly/YYYY-WNN/slate.csv \
  --market weekly/YYYY-WNN/market/<snapshot>/market.csv \
  --as-of 2026-09-05T16:00:00Z \
  --output-dir weekly/YYYY-WNN/recommendations-current
```

Without `--market`, recommendations fall back to moneylines on the slate CSV.
Prefer `--market` for production baseline cards.

Outputs (in the chosen output directory):

- `recommendations.csv`
- `card.md`
- `run_manifest.json`

Directories containing a `FINALIZED` marker must not be overwritten.

### Tiebreaker

```bash
pick-prophet weekly tiebreaker \
  --slate weekly/YYYY-WNN/slate.csv \
  --market weekly/YYYY-WNN/market/<snapshot>/market.csv \
  --game-id <cfbd_game_id> \
  --as-of 2026-09-05T16:00:00Z \
  --output-dir weekly/YYYY-WNN/tiebreaker
```

Uses the consensus market total baseline and writes `tiebreaker.json` plus
`tiebreaker.md`.

### Review checklist

Preserve the quantitative baseline. Review, do not auto-blend:

- close market probabilities
- material line movement versus prior snapshot / ESPN screenshot odds
- FPI / SP+ / Elo disagreement from the signals snapshot
- quarterback availability
- consequential injuries or suspensions
- venue and severe weather

Public-pick percentages are comparison context only in a standard league.
Do not invent confidence-point rankings for a standard league.

Document qualitative findings in `context.md` (or an append-only review note).
Any override must cite sources, timestamps, and rationale separately from the
baseline recommendation files.

## 4. Final-card preparation

Produce `final_card.md` and `final_picks.csv` **only after explicit user
authorization to finalize picks**.

Rules:

1. Start from the authorized market-baseline recommendation set.
2. Keep baseline picks/probabilities intact in recommendation artifacts.
3. Record overrides in `final_picks.csv` using `manual_override` and
   `review_note` (see Week 1 example).
4. Include the authorized tiebreaker integer total.
5. Label the card as the human/final decision document, distinct from
   `card.md` produced by `weekly recommend`.

There is currently **no** CLI that emits the final card. Create or update these
files carefully by hand (or future tooling), without rewriting baseline outputs.

## 5. Submission recording

**Capability gap:** no `weekly finalize` / submission CLI exists yet.

After the user confirms ESPN entry (or an authorized submission action
succeeds), record at least:

- exact submitted winners per game
- submitted tiebreaker total
- submission timestamp (UTC)
- whether the submission matched `final_picks.csv`

Proposed location: `weekly/YYYY-WNN/submission.json` (and optional screenshot
hash notes). Do not claim submission occurred without confirmation.

## 6. Pre-lock recheck

1. Refresh or re-identify latest market/signals snapshots (respecting gaps above).
2. Optionally re-run `weekly recommend` and `weekly tiebreaker` into a **new**
   output directory (for example `recommendations-prelock-<stamp>/`).
3. Compare against the recorded submitted card.
4. Never silently mutate submitted selections or overwrite a finalized
   recommendation directory.
5. If a change is warranted, propose it, obtain authorization, then record the
   authorized change and new submission evidence.

## 7. Postgame grading

**Capability gap:** `pick-prophet weekly grade` is planned in
`docs/implementation_plan.md` but not implemented.

Until that command exists, capture results manually into proposed artifacts
under `weekly/YYYY-WNN/results/` and compute:

- correct picks / total accuracy
- baseline versus override performance
- tiebreaker actual total and absolute error

Do not alter historical slate, market, signal, or recommendation inputs when
feeding findings into later analysis.

## Command index (verified)

```bash
pick-prophet weekly validate-slate PATH [--as-of AS_OF]
pick-prophet weekly recommend --slate SLATE [--market MARKET] --as-of AS_OF [--output-dir OUTPUT_DIR]
pick-prophet weekly fetch-signals --slate SLATE [--snapshot SNAPSHOT]
pick-prophet weekly tiebreaker --slate SLATE --market MARKET --game-id GAME_ID --as-of AS_OF --output-dir OUTPUT_DIR
```

Related research CLIs (not weekly contest modes): `ingest`, `build`, `analyze`,
`analyze-early-season`.
