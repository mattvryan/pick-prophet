# Historical market contract (M04)

Status: protocol for CFBD historical lines and future timestamped snapshots.

## Observation roles

| Role | Meaning | When usable |
|---|---|---|
| opening | First available pre-game quote | Requires `observed_at` **or** a provider-labeled open field (`spreadOpen` / `overUnderOpen`) |
| latest_prelock | Last quote at/before contest lock | Requires `observed_at` and lock/kickoff timestamps |
| closing | Last quote at/before kickoff | Requires `observed_at`; otherwise CFBD `/lines` are treated as **closing-like** |

**Hard rule:** never infer opening vs closing from array order when timestamps
are missing. CFBD historical payloads currently omit observation times; the
builder labels them `cfbd_historical_closing_like_no_observation_timestamp`.

## Aggregation

- Spreads and totals: median across retained provider quotes.
- Moneylines: convert each American price to an implied probability, take the
  median probability, convert back. Never average American odds arithmetically.
- Two-way vig removal yields `home_implied_prob`.
- `home_market_logit` is the bounded logit of that probability.
- Missing one side of a moneyline leaves probability/logit null.
- Spread/total **never** fabricate a moneyline probability
  (`moneyline_fabricated_from_spread=false` always).

## Point-in-time filtering

When `observed_at` is present, quotes after kickoff are rejected and counted in
`post_kick_provider_quotes_rejected`. Untimestamped quotes are kept for CFBD
compatibility but cannot support true PIT ordering.

## Line movement candidates

When both labeled open and consensus close values exist:

- `spread_move_home = spread_home - spread_home_open`
- `total_move = total - total_open`

These are feature candidates, not proof of continuous time series.

## Coverage

Use `provider_coverage_rows()` on raw `/lines` payloads to summarize
provider × season × week quote counts for audits.

## Regenerating market-only baselines

Under evaluation protocol 1.0.0:

```bash
pick-prophet evaluate --input data/processed/games_2017_2025.csv --protocol 1.0.0
# or season files after rebuild:
pick-prophet build --season 2025
pick-prophet analyze --input data/processed/games_2025.csv
```

Market-only scoring uses `home_implied_prob` / `home_market_logit` on rows where
two-way moneylines exist; spread-only rows remain explicitly uncovered for
calibrated probability.
