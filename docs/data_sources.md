# Data-source audit

Status reflects availability as of 2026-09-04.

| Source | Fields | Historical / point-in-time | Access | Decision |
|---|---|---|---|---|
| CollegeFootballData | schedules, results, venue, conferences, lines, polls, FPI, SP+, SRS, Elo, coaches | Strong; weekly ratings/polls and game-level odds | API key; free tier currently advertises historical data and betting lines | Primary backbone |
| ESPN public score API | scores, records, rankings, venue metadata | Historical scoreboards can be queried, but the endpoint is undocumented | No formal contract | Validation/fallback only; do not make pipeline depend on it |
| Massey Ratings archive | Massey ratings and comparison rankings | Season archives exist | Web archive; licensing/format stability must be confirmed | Deferred adapter |
| Sagarin | ratings | Historical pages are inconsistently archived | No documented data API | Deferred; seek licensed archive or preserved snapshots |
| ESPN Pick'em | contest slate, public pick %, expert picks | No stable documented historical archive found | Current contest UI/private endpoints may change | Missing critical source; import preserved snapshots manually |

## CFBD field coverage

The API is used for `/games`, `/lines`, `/rankings`, `/ratings/fpi`,
`/ratings/sp`, and `/ratings/elo`. Raw responses are saved before transformation.
The free tier currently lists basic historical data, betting lines, and advanced
metrics, but limits and endpoint entitlements can change.

## Acquisition strategy for missing Pick'em data

1. Export any existing league/personal ESPN history and browser network captures.
2. Search dated Internet Archive snapshots of weekly contest pages.
3. Ask pool members for screenshots or weekly emails; transcribe with two-person
   verification.
4. Beginning now, capture each slate and its percentages at a fixed timestamp,
   save the raw payload/screenshot, and record `captured_at` and `source_url`.
5. Never infer historical slate membership from nationally televised games; that
   creates selection bias.

Use `data/external/pickem_slate_TEMPLATE.csv` as the import contract. Unknown
public percentages stay null. Validate with
`pick-prophet pickem validate-import PATH` (confirmed rows require two distinct
verifiers). Track archive search progress in `docs/pickem_inventory.md`.

## Important limitations

- A final closing line is a legitimate benchmark for a contest locked near
  kickoff, but is leakage for picks locked earlier. Store both observation and
  kickoff timestamps when odds snapshots are available. See
  `docs/market_contract.md` for the M04 historical market contract (vig-free
  probabilities, bounded logits, open-field movement, post-kick rejection).
- CFBD's consensus providers and coverage vary by game and season. The builder
  records provider counts and never treats missing odds as pick'em lines.
- Ratings joined to week *w* must be published before the game. CFBD's current
  FPI and SP+ endpoints are season-level, so those values remain unjoined until
  dated weekly archives are available. Elo is requested weekly and joined from
  week *w - 1*. Entering W-L, previous result, and SOS are derived only from
  prior completed games in the same season (see `attach_history_features`).
  Poll ranks and weekly Elo joins that must use team **names** emit
  `*.name_join_audit.csv` beside the processed season table.
- Ratings feasibility and temporal semantics (M06 memo): see
  `docs/ratings_feasibility.md`. Adapter implementation is deferred.
- Modeling feature matrix (M07): see `docs/matrix_schema.md`. Ratings remain
  deferred in the matrix manifest inventory until an approved adapter PR.
- Live CFBD smoke checks are manual only; see `docs/cfbd_live_smoke.md`.
- Returning-QB status, rivalry labels, and coach tenure need separately sourced,
  season-specific tables; current rosters must never be projected backward.
  Massey/Sagarin remain deferred pending licensing.
