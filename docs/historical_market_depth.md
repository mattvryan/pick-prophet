# M16 historical market depth and timing

Status: **complete with external-access stop condition**
Protocol: `2.0.0`

## Finding

The local matrix contains historical CFBD closing-like observations but no
provider observation timestamp. Consequently, it cannot establish an exact
opening/latest-prelock sequence, and its empty movement columns remain
unavailable rather than imputed.

Two publisher-documented products appear technically suitable:

- [The Odds API historical odds](https://the-odds-api.com/liveapi/guides/v4/)
  documents timestamp-selected historical snapshots, NCAAF featured-market
  coverage from mid-2020, and paid-plan access.
- [SportsDataIO NCAA football workflow](https://sportsdata.io/developers/workflow-guide/ncaa-football)
  documents timestamped opening, movement, and closing prices; its older odds
  reside in a separately accessed historical warehouse.

Both require commercial access or sales/subscription decisions. No purchase,
trial acceptance, or restricted data retrieval was performed.

## Decision

- Keep the current market baseline labelled
  `cfbd_historical_closing_like_no_observation_timestamp`.
- Do not create opening, latest-prelock, dispersion, or movement features from
  undated values.
- M20 schema 2.0 may carry market-depth audit fields, but they remain unavailable
  for modeling unless a later authorized import passes the contract below.

## Future import contract

Every quote must include canonical game ID, provider, explicit UTC observation
timestamp, and both moneyline sides. The importer must additionally retain
source event/team IDs, kickoff timestamp, spread/total when present, retrieval
timestamp, immutable snapshot hash, license/redistribution classification, and
identity-review status. Latest-prelock selection is strictly `observed_at_utc <=
game_lock_utc`; post-lock values are retained only in rejection audit output.

Before purchasing access, request a small contractual sample and measure NCAAF
game matching, FBS coverage, moneyline availability, provider continuity, true
snapshot frequency, and total historical retrieval cost.
