# M06 ratings feasibility and temporal semantics design

Date: 2026-09-04
Status: approved for implementation planning
Roadmap: `docs/modeling_implementation_roadmap.md` § M06
Branch: `data/m06-pit-ratings`

## Problem

M07+ needs approved point-in-time rating features, but historical FPI/SP+
remain structurally unjoined and Elo currently mixes game-level pregame fields
with weekly `/ratings/elo` fallback without a documented canonical rule or
publication-time proof. Shipping adapters before source review risks illegal
redistribution, silent leakage, or false confidence from numeric agreement.

## Goals

1. Produce a feasibility memo covering CFBD Elo, CFBD FPI, CFBD SP+,
   sportsdataverse weekly FPI, and any credible weekly SP+ archive found during
   research.
2. For each source, document: availability by season/week; effective vs
   publication vs retrieval time; retrieval method; licensing/redistribution;
   stable identifiers; expected coverage; revision behavior; whether values can
   be joined strictly before kickoff.
3. Empirically compare game-level `home_pregame_elo` / `away_pregame_elo` to
   weekly `/ratings/elo` at week *w−1* on local CFBD snapshots, including Week 1
   / preseason semantics, without treating agreement as publication-time proof.
4. End with a per-source recommendation: **implement**, **investigate further**,
   or **omit**.
5. Mark roadmap: **M06 feasibility memo complete; adapter implementation deferred.**
6. Keep CI green with synthetic fixtures; treat local-snapshot regeneration as
   an acceptance workflow.

## Non-goals (this PR)

- No production adapters or join changes (`build.py` untouched).
- No new third-party package dependencies.
- No CLI production wiring that joins ratings into weekly cards.
- No large row-level Elo comparison dumps in git.
- No figures unless a table fails to convey Week 1 / disagreement patterns.
- Follow-up adapter work must use **separate branches** after human review of
  the memo recommendations.

## Approach

**Memo + offline comparison harness (Approach 2), refined:**

| Artifact | Role |
|---|---|
| `docs/ratings_feasibility.md` | Canonical memo + recommendations |
| `docs/ratings_elo_pregame_vs_weekly.csv` | Aggregate season×week comparison only |
| `docs/ratings_elo_pregame_vs_weekly.provenance.json` | Mandatory machine-readable provenance for the aggregate CSV |
| Research helper (not imported by build/CLI production) | Deterministic aggregation for acceptance runs |
| Synthetic fixtures + unit tests | CI coverage of aggregation and Week 1 edges |
| Roadmap M06 status line | Exact deferred wording above |

## Source evaluation contract

Every source section in `docs/ratings_feasibility.md` must fill:

1. **Availability** — seasons and week granularity (or season-level only).
2. **Temporal fields** — what constitutes effective time, publication time, and
   retrieval time; which are absent.
3. **Retrieval** — endpoint, archive URL pattern, or manual capture path.
4. **Licensing / redistribution** — whether we may store raw snapshots and
   derived features in-repo or only behind local/private retention.
5. **Stable identifiers** — team_id vs name; game_id linkage if any.
6. **Coverage** — expected FBS completeness for research window 2017–2025.
7. **Revision behavior** — end-of-season overwrite, retrospective backfill,
   contemporaneous-only flags (when documented by publisher).
8. **Join-before-kickoff** — can an adapter select the latest observation with
   effective/publication time strictly before `kickoff_utc`?
9. **Recommendation** — `implement` | `investigate further` | `omit`, with one
   paragraph of rationale.

Every factual conclusion about endpoint parameters, temporal semantics,
licensing/redistribution, and revision behavior must cite a primary source when
one is available. Clearly label inferences and unresolved facts. Absence of a
documented restriction must not be interpreted as permission to redistribute.

### Sources in scope

| Source | Notes for this PR |
|---|---|
| CFBD Elo | `/ratings/elo` (weekly) + game `home_pregame_elo` / `away_pregame_elo` |
| CFBD FPI | `/ratings/fpi` (document year-only params; no week) |
| CFBD SP+ | `/ratings/sp` (same season-level constraint) |
| sportsdataverse weekly FPI | Docs/archive metadata only; **do not** add the package |
| Credible weekly SP+ archive | Literature/web search (e.g. publisher pages, FO archives, sheets); document if found or state none credible for PIT |

## Elo canonical decision (memo only)

**Current production behavior (document, do not change):** builder prefers game
pregame Elo fields, then falls back to weekly Elo at `feature_week = max(week - 1, 0)`
via team **name** (audited).

**Empirical comparison (acceptance, local snapshots):**

- Join each FBS game’s pregame Elo to the weekly Elo row for the same team at
  week *w−1* (and document Week 1 / week-0 / missing weekly rows separately).
  The canonical comparison key is `(season, season_type, week, team_id)`.
  A normalized team name may be used only as an explicitly audited fallback
  when a stable ID is unavailable. The helper must never match across seasons
  or season types.
- Emit **aggregate** rows only: `season`, `season_type`, `week`, total sides,
  both-present count, exact-match count/rate, within-tolerance count/rate,
  mean/median/p90/p95/maximum absolute delta, per-source null counts/rates, and
  side-specific anomaly counts. Exact equality and tolerance matching are
  separate metrics, and the configured tolerance must be explicit.
- Commit `docs/ratings_elo_pregame_vs_weekly.csv` from a local acceptance run
  when raw trees exist; regenerate via documented command.
- The mandatory machine-readable provenance sidecar must record: exact raw
  snapshot paths and content hashes, the deterministic snapshot-selection rule,
  generation timestamp (UTC), helper module/script path and content hash or git
  blob identity, repository revision when available, seasons and season types
  included, parameters and tolerance, input/output row counts, exclusions, and
  identical/conflicting duplicate counts.

**Hard interpretation rule:** numeric agreement is evidence that the two CFBD
surfaces often carry the same number; it **does not** prove either surface’s
publication time relative to kickoff. The memo must say this explicitly.

**Week 1 / preseason semantics (required analysis):**

- Behavior when `week == 1` and `feature_week == 0`.
- Whether weekly Elo payloads include week 0 / preseason rows in local
  snapshots.
- How often pregame fields are present when weekly *w−1* is missing (and the
  reverse).
- Call out any asymmetry that would make one surface safer for a future
  adapter even if overall agreement is high.

**Recommendation output:** choose a preferred canonical Elo surface for a
*future* adapter PR (or “investigate further” if evidence is inconclusive),
without modifying `build.py`.

## Comparison harness shape

```text
src/pick_prophet/research/elo_pregame_vs_weekly.py
  load_games(snapshot) -> rows with kickoff, week, team names, pregame elo
  load_weekly_elo(snapshot) -> (season, season_type, week, team_id) -> elo
  compare_side(...) -> per-game side records (in memory only)
  aggregate(season, week, sides) -> season×week summary dict
  write_aggregate_csv(path)
  write_provenance(path or memo section)
```

- Production `features/build.py`, ingest, and weekly recommend paths must not
  import this helper.
- Duplicate weekly rows that are identical after normalization may be
  deduplicated, but the count must be audited. Conflicting values for the same
  canonical key must produce an explicit error or documented exclusion; input
  ordering must never determine the selected rating.
- CI uses synthetic committed fixtures that include Week 1, mid-season match,
  mid-season mismatch, missing weekly / missing pregame cases, identical and
  conflicting duplicates, multiple seasons, and regular/postseason week-number
  collisions.
- Optional thin CLI or `python -m` entry for acceptance only is allowed if it
  does not register as a production subcommand required for cards.

## CI vs acceptance

| Mode | Input | Asserts |
|---|---|---|
| CI | `tests/fixtures/ratings_elo_compare/` (synthetic) | Aggregation math, Week 1 bucketing, provenance fields present, no row-level dump required |
| Acceptance | Explicitly selected local `data/raw/cfbd/{season}/{snapshot}/` paths | Regenerates aggregate CSV + provenance using the documented selection rule; operator reviews memo tables |

## Roadmap / docs updates

- `docs/modeling_implementation_roadmap.md` § M06: status
  **“M06 feasibility memo complete; adapter implementation deferred.”**
- Cross-link memo from `docs/data_sources.md` (short pointer only).
- Update `docs/schema.md` so `elo_home` / `elo_away` accurately describe the
  current preference for game-specific pregame Elo and the weekly *w−1*
  fallback. This is documentation only; do not change join behavior.
- Do not mark FPI/SP+/Elo adapters implemented.

## Tests and acceptance

- Unit tests on synthetic fixtures: Week 1 aggregation, exact-match vs
  within-tolerance metrics, delta distribution, missing weekly, missing
  pregame, identical duplicate auditing, conflicting duplicate rejection,
  multi-season isolation, and regular/postseason isolation.
- Memo checklist complete for every in-scope source, with primary citations for
  factual claims where available and explicit `inference` / `unknown` labels
  otherwise.
- Aggregate CSV committed with provenance; no row-level dump in git.
- `build.py` diff empty for join logic.
- Roadmap wording exact as above.

## Open follow-ups (out of this PR)

- Adapter PRs per approved source (separate branches).
- Any licensing counsel / redistributor permission for sportsdataverse or
  publisher SP+ weekly captures.
- Re-probe CFBD if API gains weekly FPI/SP+ parameters later (new memo revision
  or adapter design, not silent join).
