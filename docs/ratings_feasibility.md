# Ratings source feasibility and temporal semantics (M06)

Date: 2026-09-04
Status: feasibility memo complete; adapter implementation deferred
Design: `docs/superpowers/specs/2026-09-04-m06-ratings-feasibility-design.md`
Roadmap: `docs/modeling_implementation_roadmap.md` § M06
Branch: `data/m06-pit-ratings`

## 1. Purpose, non-goals, and the hard interpretation rule

### Purpose

M07+ needs point-in-time (PIT) rating features. Before any adapter is written,
each candidate rating source must be reviewed for availability, temporal
semantics, retrieval path, licensing, identifiers, coverage, revision behavior,
and whether a value can be joined strictly before kickoff. This memo is that
review. It ends with a per-source `implement` / `investigate further` / `omit`
recommendation and a canonical Elo recommendation for a *future* adapter PR.

### Non-goals

This PR ships **no adapters and no join changes**. Specifically:

- `src/pick_prophet/features/build.py` join logic is unchanged.
- No new third-party package dependency is added (no `sportsdataverse`, no
  `cfbfastR`).
- No ratings are wired into weekly cards.
- `docs/schema.md` and the roadmap status line are handled as a separate task.

### Hard interpretation rule

> **Numeric agreement between two rating surfaces is not proof of publication
> time.** When game-level `home_pregame_elo` and weekly `/ratings/elo` at week
> *w−1* carry the same number, that is evidence the two CFBD surfaces often
> expose the same value. It says **nothing** about when either surface was
> computed or published relative to kickoff. Neither surface carries a
> publication timestamp, so agreement cannot be upgraded into a leakage
> guarantee.

Three corollaries are applied throughout this memo:

1. **Absence of a documented restriction is not permission.** Where licensing
   terms are silent or ambiguous, the source is labeled `unknown`, not
   `permitted`.
2. **Unresolved facts are labeled.** Claims are tagged `inference` where they
   are our reasoning rather than a publisher statement, and `unknown` where no
   primary source could be found. Everything else cites a primary source.
3. **Computation time is not publication time.** A field documenting *when a
   provider computed a value* bounds what information could have entered that
   value; it does not establish when the value became retrievable by a
   consumer. Publication/availability time is recorded as `absent` or `unknown`
   unless a primary source states it. This memo therefore never reports a
   computation timestamp under the "publication timestamp" heading.

## 2. Current production Elo behavior (documented, not changed)

The builder resolves `elo_home` / `elo_away` in two stages.

**Stage 1 — game-level pregame Elo (preferred).** The game record's
`home_pregame_elo` / `away_pregame_elo` fields are read directly onto the row:

```153:154:src/pick_prophet/features/build.py
            "elo_home": _get(game, "home_pregame_elo", "homePregameElo"),
            "elo_away": _get(game, "away_pregame_elo", "awayPregameElo"),
```

**Stage 2 — weekly Elo fallback at `max(week - 1, 0)`.** Only when the stage-1
field is `None` does the builder consult the weekly `/ratings/elo` index, keyed
by **team name**, and every attempt is written to the name-join audit:

```157:158:src/pick_prophet/features/build.py
        # Use the preceding week. This conservative join avoids post-game values.
        feature_week = max(week - 1, 0)
```

```189:204:src/pick_prophet/features/build.py
        for name, index in ratings.items():
            if row.get(f"{name}_home") is None:
                value = index.get((feature_week, home))
                row[f"{name}_home"] = value
                _audit_name_join(
                    name_join_audit,
                    game_id=game_id,
                    season=row["season"],
                    week=week,
                    side="home",
                    feature=name,
                    team_name=home,
                    team_id=home_id,
                    resolved=value is not None,
                    reason="weekly rating endpoint keyed by team name; no game-level ID",
                )
```

The weekly index itself is keyed `(week, team_name)` with no season-type
component:

```56:64:src/pick_prophet/features/build.py
def _rating_index(
    rows: list[dict[str, Any]], value_key: str
) -> dict[tuple[int, str], float]:
    result = {}
    for row in rows:
        value = row.get(value_key, row.get("rating"))
        if value is not None and row.get("week") is not None:
            result[(int(row["week"]), row["team"])] = float(value)
    return result
```

FPI and SP+ are deliberately **not** joined; they are retained raw-only:

```102:105:src/pick_prophet/features/build.py
    # Do not join season-level FPI/SP+ snapshots to historical games: a pull made
    # after the season contains future information. They remain raw-only until a
    # genuinely dated weekly archive is available.
    ratings = {"elo": _rating_index(load("elo"), "elo")}
```

### How the local weekly Elo snapshot is captured

The ingest adapter treats Elo as the one weekly ratings endpoint and requests it
once per week for weeks 1–20 with `seasonType=both`, stamping the **requested**
week onto each returned row:

```208:222:src/pick_prophet/ingest/cfbd.py
            if endpoint.weekly:
                payload = []
                for week in week_list:
                    rows = client.get(
                        endpoint.path,
                        {"year": season, "week": week, "seasonType": "both"},
                    )
                    if not isinstance(rows, list):
                        raise ValueError(
                            f"CFBD {endpoint.name} week {week}: expected array"
                        )
                    for row in rows:
                        if isinstance(row, dict):
                            row.setdefault("week", week)
                    payload.extend(rows)
```

Three consequences follow directly, and they explain most of the empirical
results in § 3:

1. **Week numbering starts at 1.** `_resolve_weeks` returns
   `range(1, max_week + 1)`, so week 0 is never requested and no week-0 row can
   exist locally. A `feature_week` of 0 therefore always misses.
2. **The stored `week` is the request's filter value, not a publisher-provided
   as-of week.** CFBD's `week` parameter is a *maximum* week filter, so the row
   labeled week *W* means "Elo as of the latest available week ≤ *W*" rather
   than "Elo published in week *W*" (see § 4.1).
3. **`seasonType=both` widens the filter.** The legacy CFBD swagger documents
   `seasonType` on `/ratings/elo` as the "Maximum season type to consider",
   which means the combination `week=W, seasonType=both` has semantics that are
   not fully specified for postseason rows. Whether a postseason-computed rating
   can be returned under a low `week` filter is **unknown** and would need an
   explicit probe before an adapter relies on it.

## 3. Empirical Elo comparison summary

Artifacts (committed):

- Aggregate results: `docs/ratings_elo_pregame_vs_weekly.csv`
- Provenance sidecar: `docs/ratings_elo_pregame_vs_weekly.provenance.json`
- Helper: `src/pick_prophet/research/elo_pregame_vs_weekly.py` (research only;
  not imported by `features/build.py`, ingest, or the weekly recommend path)

Run parameters, from the provenance sidecar: seasons 2017–2025, season types
`regular` / `postseason` / `spring_regular`, tolerance 1.0 Elo point, snapshot
selection rule `lexicographic_max_subdir_with_games_and_elo_json`, 7,763 input
game rows → 15,526 sides → 149 aggregate rows, 15,617 non-FBS games excluded,
0 identical duplicates and 0 conflicting duplicates.

### 3.1 Regular-season weeks ≥ 2: agreement is high but decays after 2020

Mean is taken across the season's week groups that have at least one
both-present side. `max |Δ|` and `max p95` are the worst single week group in
the season.

| Season | Week groups | Mean exact-match rate | Min exact-match rate | Mean within-tolerance (±1.0) | Max p95 \|Δ\| | Max \|Δ\| |
|---|---:|---:|---:|---:|---:|---:|
| 2017 | 14 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| 2018 | 14 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| 2019 | 14 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| 2020 | 15 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| 2021 | 14 | 0.990 | 0.961 | 0.990 | 0 | 268 |
| 2022 | 14 | 0.909 | 0.574 | 0.917 | 23 | 169 |
| 2023 | 14 | 0.912 | 0.543 | 0.913 | 160 | 342 |
| 2024 | 15 | 0.933 | 0.687 | 0.937 | 20 | 157 |
| 2025 | 15 | 0.915 | 0.590 | 0.926 | 30 | 65 |

Readings:

- **2017–2020 agree perfectly** on every both-present side. For these seasons
  the two surfaces are numerically interchangeable in our snapshots.
- **2021 is a transition year**: 99% exact overall, but individual weeks fall to
  0.961 and one week shows a 268-point maximum delta. Rare, large disagreements
  coexist with near-perfect medians.
- **2022–2025 sit at roughly 0.91–0.93 mean exact-match**, with early-season
  week groups collapsing to **0.543–0.687**. Median absolute delta stays at 0.0
  in every one of these weeks, so the disagreement is concentrated in a minority
  of teams rather than spread across the slate.
- **Tolerance adds almost nothing.** A ±1.0 Elo tolerance moves the rate by at
  most ~0.02 in any season, because the deltas are either exactly 0 or large.
  Exact-match and within-tolerance are reported as separate metrics and behave
  nearly identically here.
- **The worst disagreements are early-season**, which is consistent with the
  weekly endpoint's maximum-week filter resolving differently while few games
  have been played. This is an `inference`, not a documented behavior.

None of the above is evidence about publication timing. See the hard
interpretation rule in § 1.

### 3.2 Week 1 and preseason semantics

For **every** regular Week 1 group in 2017–2025, `weekly_null_rate = 1.0`:

| Season | Week 1 sides | `weekly_null_rate` | `pregame_null_rate` | `n_pregame_only` |
|---|---:|---:|---:|---:|
| 2017 | 182 | 1.0 | 0.495 | 92 |
| 2018 | 176 | 1.0 | 0.477 | 92 |
| 2019 | 170 | 1.0 | 0.459 | 92 |
| 2020 | 18 | 1.0 | 0.444 | 10 |
| 2021 | 178 | 1.0 | 0.438 | 100 |
| 2022 | 188 | 1.0 | 0.218 | 147 |
| 2023 | 188 | 1.0 | 0.223 | 146 |
| 2024 | 200 | 1.0 | 0.305 | 139 |
| 2025 | 192 | 1.0 | 0.255 | 143 |

Cause, confirmed against the local payload: weekly Elo rows carry weeks 1–20
only, because ingest requests `range(1, 21)` and stamps the requested week.
Week 1 games map to `feature_week = max(1 - 1, 0) = 0`, and **no week-0 row
exists**, so the fallback can never resolve. There is no preseason row in the
local snapshots to fall back to.

The asymmetry matters more than the null rate. Across all 1,492 regular Week 1
sides, the weekly surface supplies **zero** values while the game-level pregame
field supplies 961 (64%); `n_pregame_only` is elevated in every season and
`n_weekly_only` is 0. Week 1 coverage comes entirely from the game-level
surface.

**Postseason is the same failure, and it is total.** CFBD postseason games carry
`week = 1`, so `feature_week = 0` again. Every postseason group in every season
shows `weekly_null_rate = 1.0`, `pregame_null_rate = 0.0`, and
`n_pregame_only = n_sides` (80, 78, 80, 52, 76, 84, 84, 92, 92 sides for
2017–2025). The game-level field has perfect postseason coverage; the weekly
fallback has none. A second, independent reason the postseason fallback cannot
work is that local weekly rows have no `seasonType` field at all, so the
research helper normalizes them to `regular` (`DEFAULT_SEASON_TYPE = "regular"`)
and a `postseason` game key can never match a weekly key.

**`spring_regular` (2020, weeks 3 and 5, 2 sides each)** has
`pregame_null_rate = 1.0` and `weekly_null_rate = 1.0` — neither surface covers
it. Any adapter should exclude spring season types rather than treat them as
missing data.

### 3.3 Identifier findings

Across all 149 aggregate groups, `n_name_fallback_joins` equals
`n_sides − n_weekly_null` exactly (12,433 = 12,433, with zero mismatched
groups). **Every** weekly Elo join in this comparison resolved through the
audited **name** fallback and **not one** resolved by team ID.

The reason is structural: the local CFBD weekly Elo payload carries only
`{conference, elo, team, week, year}`. There is no `team_id` / `teamId` field,
no `seasonType` field, and no timestamp field. The v2 response schema for
`/ratings/elo` confirms this at the contract level — it returns `year`, `team`,
`conference`, and `elo`, and nothing else.[^cfbd-ratings-v2]

This is the single largest structural weakness of the weekly surface: it is
name-keyed by construction, so every join needs the name-audit trail, and CFBD
explicitly disclaims any guarantee of stable identifiers.[^cfbd-terms]

## 4. Source dossiers

Each dossier answers items 1–9 of the design's source evaluation contract.

### 4.1 CFBD Elo — game-level pregame fields (`/games`)

1. **Availability.** Per-game, all seasons in the 2017–2025 research window,
   both regular and postseason. Coverage is empirically excellent: 0% null in
   every postseason group, and 22–50% null only in regular Week 1 (§ 3.2).
2. **Temporal fields.** *Effective time*: implied by the field name to be the
   team's rating immediately before this specific game — the game record fixes
   the effective moment, which is its own advantage over a week-numbered
   surface. *Publication time*: **absent.** No `published_at`, `computed_at`, or
   `as_of` field exists on the game record. *Retrieval time*: recorded by us in
   the snapshot manifest (`retrieved_at`), not by CFBD.
3. **Retrieval.** `GET /ratings` is not involved; the fields arrive with
   `GET /games?year={season}`, already ingested as `games.json` in each snapshot
   (`Endpoint("games", "/games")`).
4. **Licensing / redistribution.** CFBD's Terms permit private caching,
   storage, normalization, and retention of API responses, plus publication and
   commercialization of Derived Outputs.[^cfbd-terms] They **prohibit**
   publishing or providing API Data as a standalone dataset or bulk download and
   prohibit giving third parties programmatic access to stored raw
   responses.[^cfbd-terms] *Practical rule for this repo:* raw snapshots stay
   local/private and out of any public bulk-download surface; committed
   artifacts must be aggregates or derived features, which is why
   `docs/ratings_elo_pregame_vs_weekly.csv` is aggregate-only. Attribution is
   appreciated but not required.[^cfbd-terms]
5. **Stable identifiers.** Strong. The game record carries `id` (game_id) plus
   `home_id` / `away_id` team IDs alongside the Elo fields, so the rating is
   linked to a game and to team IDs **without any name join**. This is the
   decisive identifier advantage over the weekly endpoint.
6. **Coverage.** Complete for FBS postseason; ~64% of regular Week 1 sides;
   effectively complete from Week 2 onward (regular-week `pregame_null_rate`
   drops to ~0.00–0.03 by mid-season in every studied year).
7. **Revision behavior.** **Unknown.** CFBD states that no field, endpoint,
   correction schedule, availability level, or stable identifier is
   guaranteed.[^cfbd-terms] We have not established whether a re-pull of a past
   season's `/games` returns byte-identical pregame Elo. `inference`: because
   our snapshots are immutable and hashed, a future re-pull *can* be diffed
   against them to answer this — that probe is a prerequisite for `implement`.
8. **Join-before-kickoff.** Not strictly demonstrable. An adapter can join by
   `game_id` with no ambiguity about *which game* the rating belongs to, but
   because there is no publication timestamp, it cannot assert the value was
   computed before `kickoff_utc`. The `pregame` naming is a publisher label, not
   a verifiable as-of guarantee.
9. **Recommendation: `investigate further`.** This is the strongest surface on
   availability and identifiers, and it is already what production prefers. It
   still falls short of `implement` on the one axis that matters most for a PIT
   feature: there is no publication timestamp, so the "pregame" claim rests
   entirely on CFBD's field naming. Per the design's resolution — prefer
   `investigate further` when publication timestamps are missing — it cannot be
   promoted yet. The concrete gate is small and mechanical: (a) re-pull one or
   two past seasons and diff pregame Elo against the existing hashed snapshots
   to characterize revision behavior, and (b) obtain a publisher statement (docs
   or Discord/maintainer confirmation) that pregame Elo is computed from
   information available before that game. If both clear, this becomes
   `implement` in the adapter PR.

### 4.2 CFBD Elo — weekly endpoint (`/ratings/elo`)

1. **Availability.** Weekly. `/ratings/elo` is the **only** CFBD ratings
   endpoint that accepts a `week` parameter.[^cfbd-ratings-v2][^cfbd-swagger]
   Locally: weeks 1–20 per season, 2,720 rows for 2025. **No week-0 or preseason
   row exists** in our snapshots (§ 3.2).
2. **Temporal fields.** *Effective time*: week-numbered, and the number is a
   **maximum** filter, not an as-of stamp. The v2 reference documents `week` as
   "Week number. Defaults to the latest available week in the
   season",[^cfbd-ratings-v2] the legacy swagger calls it "Maximum week
   filter",[^cfbd-swagger] and the official Python client repeats the v2
   wording.[^cfbd-python] `seasonType` is likewise documented in the legacy
   swagger as "Maximum season type to consider (defaults to regular if week is
   specified else defaults to postseason)".[^cfbd-swagger] *Publication time*:
   **absent** — the response has no timestamp field.[^cfbd-ratings-v2]
   *Retrieval time*: ours only, via the snapshot manifest.
3. **Retrieval.** `GET /ratings/elo?year={season}&week={w}&seasonType=both`,
   looped over weeks 1–20 and stored as `elo.json`
   (`Endpoint("elo", "/ratings/elo", weekly=True)`).
4. **Licensing / redistribution.** Identical to § 4.1 — same Terms, same
   private-retention-plus-derived-outputs rule.[^cfbd-terms]
5. **Stable identifiers.** **Weak — this is the disqualifying finding.** The
   response contract is `year`, `team`, `conference`, `elo`.[^cfbd-ratings-v2]
   No team ID, no game linkage, and no season-type discriminator in our stored
   rows. Empirically, 100% of the 12,433 successful weekly joins used the name
   fallback and 0% used an ID (§ 3.3).
6. **Coverage.** Zero for regular Week 1 and zero for all postseason
   (§ 3.2). Elevated nulls in early regular weeks 2–4; near-complete
   mid-season.
7. **Revision behavior.** **Unknown**, same disclaimer as § 4.1.[^cfbd-terms]
   The 2022–2025 disagreement with the game-level surface (§ 3.1) is consistent
   with either surface having been recomputed, but our data cannot attribute the
   difference to one of them.
8. **Join-before-kickoff.** Weaker than § 4.1 on two counts. There is no
   publication timestamp, *and* the week label is a maximum-week filter rather
   than an as-of week, so even the effective time is only approximately known.
   The `week=W, seasonType=both` combination we currently request has
   unspecified postseason behavior (§ 2), which is an open leakage question
   rather than a demonstrated leak.
9. **Recommendation: `investigate further`** — and, if the surface is used at
   all, **only as a documented fallback**, never as the primary key. It is the
   only CFBD ratings endpoint with weekly granularity, which is genuinely
   valuable, but it is name-keyed with no ID, has no timestamp, has no coverage
   at Week 1 or in the postseason, and its week semantics are a maximum filter.
   Before an adapter relies on it, three things need resolving: whether a
   week-0/preseason row is retrievable at all (a `week=0` probe was never made
   because ingest starts at 1); what `seasonType=both` returns under a low
   `week` filter; and whether a team-ID crosswalk can replace the name join.

### 4.3 CFBD FPI (`/ratings/fpi`)

1. **Availability.** **Season-level only.** The v2 reference lists exactly three
   query parameters — `year`, `team`, `conference` — and **no `week`**;[^cfbd-ratings-v2]
   the legacy swagger agrees.[^cfbd-swagger] One row per team per season.
2. **Temporal fields.** *Effective time*: the season, with no intra-season
   resolution — the endpoint exposes no field narrowing the observation to a
   week.[^cfbd-ratings-v2] *Publication time*: absent. *Computation time*:
   absent. *Retrieval time*: ours only. `inference`: a season-labeled rating
   pulled after that season most plausibly reflects end-of-season information,
   but CFBD documents nothing about when the served value is computed, so this
   is our reading rather than a publisher statement.
3. **Retrieval.** `GET /ratings/fpi?year={season}`, already ingested as
   `fpi.json` and retained raw-only (`Endpoint("fpi", "/ratings/fpi")`).
4. **Licensing / redistribution.** Same CFBD Terms.[^cfbd-terms] Additionally,
   FPI is an ESPN product and the Terms grant no third-party
   rights,[^cfbd-terms] so ESPN's own terms would govern any republication of
   FPI values as data. Effectively `unknown` for redistribution beyond derived
   outputs.
5. **Stable identifiers.** Name-keyed (`team`, `conference`); no team ID in the
   response.[^cfbd-ratings-v2]
6. **Coverage.** Believed complete at FBS season level for the research window,
   but coverage is irrelevant given the temporal defect.
7. **Revision behavior.** **Unknown.** CFBD guarantees no correction
   schedule.[^cfbd-terms] We found no primary source stating that the endpoint
   overwrites a season row in place, nor any archive of prior values, so the
   memo does **not** assert that today's value is the post-season or final
   revision — that would be an unsupported claim read off a schema.
   `inference`: since the response carries one row per team-season with no
   week, season-type, or version discriminator,[^cfbd-ratings-v2] whatever
   revision the endpoint serves is the only one obtainable, and there is no
   mechanism *in this endpoint* to recover the value as it stood in week *w*.
   Which revision that is, and whether it changes between pulls, is untested; a
   re-pull-and-diff probe against hashed snapshots would answer it.
8. **Join-before-kickoff.** **No**, and this conclusion does not depend on
   item 7. The blocking fact is documented, not inferred: the endpoint has no
   week parameter and no publication or computation timestamp, so **no
   observation can be placed before a mid-season `kickoff_utc` at all**. A
   week-*w* join would therefore be asserting a timing property that no field
   in the response supports. `inference`, and the reason the existing
   `build.py` comment is prudent: a season-labeled value most likely also
   embeds that season's later results.
9. **Recommendation: `omit`.** Not a close call, and it rests only on
   documented facts: the public CFBD FPI endpoint has no week parameter and no
   temporal field of any kind,[^cfbd-ratings-v2] so there is nothing to make
   PIT-safe — a week-*w* join would be unfalsifiable rather than merely
   unproven. It must stay raw-only and unjoined. This is a statement about
   *this endpoint*, not about FPI as a metric — see § 4.5 for the weekly FPI
   route.

### 4.4 CFBD SP+ (`/ratings/sp`)

1. **Availability.** **Season-level only.** The v2 reference lists `year` and
   `team` and **no `week`**;[^cfbd-ratings-v2] the legacy swagger shows the same
   two parameters plus `minimum: 1970`.[^cfbd-swagger] One row per team per
   season.
2. **Temporal fields.** *Effective time*: the season, with no week
   field.[^cfbd-ratings-v2] *Publication time*: absent. *Computation time*:
   absent. *Retrieval time*: ours only. Same `inference` as § 4.3 item 2 about
   end-of-season contamination, carrying the same label.
3. **Retrieval.** `GET /ratings/sp?year={season}`, ingested as `sp.json` and
   retained raw-only (`Endpoint("sp", "/ratings/sp")`).
4. **Licensing / redistribution.** Same CFBD Terms.[^cfbd-terms] SP+ is Bill
   Connelly's system, published at ESPN; no third-party rights are
   granted,[^cfbd-terms] so republication of SP+ values as data is `unknown`.
5. **Stable identifiers.** Name-keyed (`team`, `conference`); no team
   ID.[^cfbd-ratings-v2]
6. **Coverage.** Season-level FBS coverage back to 1970 per the swagger
   minimum,[^cfbd-swagger] but again irrelevant given the temporal defect.
7. **Revision behavior.** **Unknown**, exactly as in § 4.3 item 7. No primary
   source states that today's value is the final or post-season revision, and
   the memo does not claim it; CFBD guarantees no correction
   schedule.[^cfbd-terms] `inference`: with one undiscriminated row per
   team-season,[^cfbd-ratings-v2] in-season states are unrecoverable *from this
   endpoint* whichever revision is being served.
8. **Join-before-kickoff.** **No**, for the same documented reason as § 4.3
   item 8: no week parameter and no publication or computation timestamp, so no
   observation can be placed before a mid-season `kickoff_utc`. The conclusion
   is independent of item 7.
9. **Recommendation: `omit`.** Identical reasoning to FPI, and likewise
   unchanged by the item 7 relabel — the recommendation turns on documented
   absence of week granularity and timestamps, not on any assumption about
   which revision is served. Keep raw-only and unjoined.

   *Adjacent lead, explicitly not in scope.* While confirming the above, we
   noted that CFBD's newer `/ratings/core` endpoint returns `throughWeek`,
   `throughSeasonType`, and `modelVersion` in its response body even though its
   query parameters are `year` / `team` / `conference`.[^cfbd-ratings-v2] That
   is the only CFBD ratings surface observed to expose a machine-readable
   through-week and a model version. It was not evaluated here because it is
   outside the design's in-scope source list, and it is recorded only as a
   future research lead.

### 4.5 sportsdataverse weekly FPI (`cfb_fpi_weekly`) — docs only, package not installed

1. **Availability.** Weekly, one row per team-week, "with FPI and its components
   as published that week".[^cfbfastr-fpi] Published coverage is 21 seasons,
   2005–2025, plus a partial 2026, as 63 assets totaling 18.4 MB.[^sdv-fpi-release]
   This fully spans our 2017–2025 research window. Note that "as published that
   week" is the dataset's prose description of weekly cadence; it is not a
   per-row publication timestamp, and it is not treated as one below.
2. **Temporal fields.** **This is the only in-scope source with explicit
   as-of metadata**, and the distinctions are documented precisely — but note
   that none of the documented fields is a publication timestamp:
   - `run_date_time_key` — "ESPN's run key for the snapshot, as an integer
     timestamp (e.g. 20241021040000). This is the AS-OF date the snapshot
     represents, which is not the same as `last_updated` (when ESPN computed
     it)".[^cfbfastr-fpi] → *effective time*.
   - `last_updated` — when ESPN **computed** the snapshot.[^cfbfastr-fpi] →
     *computation time only*. The publisher's own wording is "when ESPN
     computed it"; nothing in the column dictionary says when the value became
     retrievable by a consumer. Per corollary 3 in § 1, this is **not** a
     publication timestamp and is not reported as one.
   - *Publication / availability time*: **absent from the documented schema,
     and `unknown`.** No reviewed primary source states when an ESPN FPI
     snapshot, or the sportsdataverse re-publication of it, first became
     available. The sportsdataverse release asset carries its own upload time,
     which is a property of the redistribution, not of the rating.
   - *Retrieval time*: ours only, and only once an adapter downloads an asset.
   - `snapshot_is_contemporaneous` — "True when the snapshot was computed inside
     its own season's window ... i.e. it is a live weekly run rather than a
     retrospective backfill. False for every row before 2015, which ESPN
     computed in one pass afterwards. A retrospective row is a reconstruction,
     not an as-of-week rating."[^cfbfastr-fpi]
   - `snapshot_out_of_sequence` — "True when this snapshot was computed AFTER
     one belonging to a later week of the same season type -- so it cannot be
     read as an as-of-that-week rating. Almost always the week-1 slot, which
     ESPN overwrites with a late-season computation (2024 week 1 is stamped
     2024-12-15). Filter these out for any point-in-time or backtest
     use."[^cfbfastr-fpi]

   The publisher therefore exposes an as-of key, a computation time, and two
   per-row PIT flags, and names the exact leakage trap while instructing
   consumers to filter it. That is more temporal metadata than any other source
   here — but it is still one step short of a publication timestamp.
3. **Retrieval.** **No package install is required**, which resolves the
   dependency concern. Release assets are "plain files on a public URL" with
   "Direct download (no auth, no API key)" at
   `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_fpi_weekly/cfb_fpi_weekly_{season}.{csv,parquet,rds}`.[^sdv-fpi-release]
   A future adapter could fetch the CSV or Parquet over plain HTTP. (The
   alternative `data.sportsdataverse.org/v1/cfb/fpi_weekly` route requires a
   bearer token.[^sdv-fpi-release])
4. **Licensing / redistribution.** **Partially known, and the gap is the
   blocker.** The `sportsdataverse-data` repository is MIT-licensed.[^sdv-license]
   `inference`: an MIT repository license covers the repository's contents as
   distributed, but the release page states the upstream source is "CFBD +
   ESPN",[^sdv-fpi-release] and a redistributor's license cannot grant rights it
   does not hold in ESPN's underlying FPI data. Whether we may commit derived
   weekly-FPI features to this repo is therefore `unknown` and needs a human
   licensing decision before an adapter ships. Absence of a restriction on the
   release page is not permission.
5. **Stable identifiers.** **Good, and better than any CFBD ratings surface.**
   The schema includes `team_id` (integer) alongside `season`, `season_type`,
   and `week`.[^cfbfastr-fpi] Because it is an ESPN team ID rather than a CFBD
   one, an adapter would need the ESPN↔CFBD crosswalk; sportsdataverse publishes
   `load_cfb_*_crosswalk()` id crosswalks for exactly this,[^cfbfastr-site] and
   a `cfb_crosswalk` release exists.[^sdv-fpi-release] That crosswalk itself
   would need its own audit.
6. **Coverage.** 2005–2025 published,[^sdv-fpi-release] but only 2015+ is
   usable for PIT work, since `snapshot_is_contemporaneous` is "False for every
   row before 2015".[^cfbfastr-fpi] For our 2017–2025 window that is not a
   limitation. FBS row-level completeness within the window is **unverified**
   here — we did not download the assets.
7. **Revision behavior.** **Documented by the redistributor, and the most
   forthcoming of any source reviewed — but unverified here.** ESPN overwrites
   the week-1 slot with a late-season computation (2024 week 1 is stamped
   2024-12-15), and pre-2015 rows are a single retrospective
   pass.[^cfbfastr-fpi] Both conditions are flagged per row rather than left for
   the consumer to discover. This is a documentation claim about ESPN's
   behavior, taken from cfbfastR's column dictionary rather than from ESPN, and
   no asset was downloaded to check it (item 9).
8. **Join-before-kickoff.** **Partially — stronger than any other source here,
   but not a proven publication-time join.** An adapter can filter to
   `snapshot_is_contemporaneous == True` and `snapshot_out_of_sequence == False`,
   then select the latest row whose `last_updated` is strictly before
   `kickoff_utc`. What that predicate buys, stated exactly:
   - It is a **computation-time** predicate. `inference`: if `last_updated` is
     accurate and row-specific, a snapshot computed before kickoff cannot
     contain that game's result, which bounds the *input* information and rules
     out the most direct form of leakage. Both conditionals are untested here
     (item 9).
   - It is **not** an availability predicate. Because publication/availability
     time is `unknown` (item 2), the join cannot assert that the value was
     retrievable before kickoff — only that it had been computed. A backtest
     using it is therefore claiming "no future results in the inputs", not
     "this is what we could have acted on at the time".
   - The as-of key plus the two PIT flags make the strict-inequality predicate
     the design asks for *expressible* rather than assumed, which is the real
     advance over the CFBD surfaces. Expressible is not the same as verified.
9. **Recommendation: `investigate further`** — unchanged, and for the same
   reason the CFBD Elo surfaces are not promoted: no publication timestamp is
   available for any in-scope source. On temporal semantics this remains the
   strongest candidate in the memo, because it is the only one that exposes a
   computation time and per-row PIT flags at all. It is held back by three
   unresolved questions: (a) the redistribution question in item 4, which needs
   a human decision on whether ESPN-derived weekly FPI may be stored and whether
   derived features may be committed; (b) the ESPN↔CFBD team-ID crosswalk in
   item 5, which introduces a second join needing its own audit trail; and
   (c) the publication/availability gap in items 2 and 8 — a computation
   timestamp is not proof that the snapshot was retrievable before kickoff, and
   no primary source establishing availability was found. A follow-up should
   also verify the timestamp fields empirically on one downloaded season before
   any adapter is designed, since every claim in items 2 and 7 is currently
   documentation-based rather than observed.

### 4.6 Credible weekly SP+ archive

Searching for a PIT-safe weekly SP+ source produced two candidate families, and
**neither is usable as a point-in-time archive**. Both are carried through the
same items 1–9 as every other dossier, answered as **(a)** ESPN's weekly SP+
articles by Bill Connelly and **(b)** sportsdataverse's `cfb_ratings_weekly`
release.

1. **Availability.**
   (a) Weekly in season, as ESPN Insider articles containing a full ratings
   table in prose — e.g. the post-Week 11 2023 installment (§ 7, leads
   consulted). There is no endpoint, feed, or dataset release; availability is
   article-by-article.
   (b) Weekly, 2004–2025, published in long format with a `through_week`
   column.[^sdv-ratings-weekly] Note before anything else that **this is not
   Bill Connelly's SP+**: the related `cfb_ratings` release describes the family
   as "SP+-**style**" opponent-adjusted ratings built by sportsdataverse over
   released play-by-play.[^sdv-ratings] Treating it as SP+ would misattribute
   the metric, so it is evaluated here only to close out the search.
2. **Temporal fields.**
   (a) *Publication time*: **present, and the only genuine one encountered in
   this memo** — the post-Week 11 2023 article is bylined "Bill Connelly, ESPN
   Staff Writer Nov 12, 2023, 12:00 PM ET" and the Week 8 2023 installment
   carries `datePublished` `2023-10-22T15:30:00Z` in syndicated metadata (§ 7).
   But it is attached to an article, not to a team row. *Effective time*: the
   week the article describes, stated in prose. *Computation time*: absent.
   (b) *Effective time*: `through_week`, and the publisher is explicit that it
   is **inclusive of week W** — "the snapshot contains games PLAYED in week W.
   To project week W, use the `through_week == W - 1` row. Filtering
   `through_week == W` and predicting week W leaks that week's results", a
   reading they verified against 2024 data at 97.0% consistency versus 58.7%
   for the exclusive reading.[^sdv-ratings-weekly] *Publication time* and
   *computation time*: **absent per row**; the ratings are a retrospective
   refit, so no row carries a contemporaneous timestamp. Per corollary 3 in
   § 1, nothing here may be reported as a publication time.
3. **Retrieval.**
   (a) Would require scraping ESPN Insider article bodies: paywalled,
   HTML-formatted prose with no stable machine-readable endpoint. Not
   reproducible.
   (b) Release assets on public URLs, the same mechanism as § 4.5 item 3.
4. **Licensing / redistribution.**
   (a) The harder problem. ESPN article content is not ours to redistribute,
   and CFBD's Terms grant no third-party rights.[^cfbd-terms] `unknown` at best
   and realistically prohibited.
   (b) `unknown`, and inherits the § 4.5 item 4 analysis: the
   `sportsdataverse-data` repo is MIT,[^sdv-license] but the ratings are built
   over upstream play-by-play, and a redistributor cannot grant rights it does
   not hold upstream. License-clearer than (a); not resolved.
5. **Stable identifiers.**
   (a) Display team names inside prose tables. No IDs, so any use would need a
   name join with a full audit trail.
   (b) **`unknown`.** The release describes long format keyed by team and
   `through_week`,[^sdv-ratings-weekly] but we did not download an asset, so
   whether a numeric team ID is present — and whose ID scheme it would be — is
   unverified.
6. **Coverage.**
   (a) `unknown` and probably incomplete. Covering 2017–2025 week by week would
   mean locating and parsing well over a hundred paywalled articles, with no
   guarantee a complete set exists or remains online.
   (b) 2004–2025 published,[^sdv-ratings-weekly] which spans the research
   window. Row-level FBS completeness is **unverified** — no asset was
   downloaded.
7. **Revision behavior.**
   (a) **`unknown`.** A published article is fixed once posted, but SP+ itself
   is recomputed weekly and no archive of corrections or restatements was
   found.
   (b) **Documented: every row is a recomputation.** "The ridge is refit on
   everything up to week W",[^sdv-ratings-weekly] so the series is a
   retrospective refit rather than a sequence of live weekly runs.
8. **Join-before-kickoff.**
   (a) **Not achievable in practice.** Article publication timestamps do
   precede the following week's kickoffs, so the timing predicate would in
   principle be expressible — but items 3 and 4 make it moot: a source we
   cannot licensably or reproducibly retrieve cannot be joined at all.
   (b) **Partially, and only on inputs.** `inference`: because the fit uses
   everything up to week W, a `through_week == W - 1` row contains no results
   from week W, so it is *input*-PIT-safe for a week-W game. It was still
   computed retrospectively with no contemporaneous publication or computation
   time, so — as in § 4.5 item 8 — this bounds input information without
   establishing that any such value existed or was available before kickoff.
9. **Recommendation: `omit`** for weekly SP+ specifically. No credible,
   reproducible, license-clear weekly SP+ archive with as-of timestamps was
   identified. The ESPN articles have publication timestamps but are
   unscrapable and unlicensable; `cfb_ratings_weekly` is license-clearer and
   PIT-tractable on inputs but is a different metric and must not be labeled
   SP+. If a future PR wants an opponent-adjusted weekly rating, it should
   evaluate `cfb_ratings_weekly` **on its own terms and under its own name**,
   using the `through_week == W - 1` rule, as a new source dossier — not as a
   stand-in for SP+.

## 5. Recommendation table

| Source | Weekly granularity | Publication timestamp | Stable ID | PIT join possible | Recommendation |
|---|---|---|---|---|---|
| CFBD game pregame Elo (`/games`) | Per game (better than weekly) | **No** | **Yes** (`game_id`, team IDs) | Game-scoped but unproven | `investigate further` |
| CFBD weekly Elo (`/ratings/elo`) | Yes (max-week filter) | No | **No** (name only) | Approximate; no Wk 1 / postseason | `investigate further` (fallback only) |
| CFBD FPI (`/ratings/fpi`) | **No** (season only) | No | No | **No** | `omit` |
| CFBD SP+ (`/ratings/sp`) | **No** (season only) | No | No | **No** | `omit` |
| sportsdataverse weekly FPI (`cfb_fpi_weekly`) | Yes | **No** — computation time only (`last_updated`); availability `unknown` | Yes (ESPN `team_id`; needs crosswalk) | Inputs only, in principle | `investigate further` |
| Weekly SP+ — ESPN articles (§ 4.6a) | Yes | Yes, but article-level paywalled prose | No | Not licensably or reproducibly | `omit` |
| Weekly SP+ — `cfb_ratings_weekly` (§ 4.6b) | Yes | No (retrospective refit, none per row) | `unknown` (not downloaded) | Inputs only, and **not SP+** | `omit` (as SP+) |

The **publication timestamp** column means publication/availability time only.
A provider-documented *computation* time does not qualify (§ 1, corollary 3);
where one exists it is named in the cell. On that reading, **no in-scope source
carries a per-row publication timestamp** — the ESPN SP+ articles are the sole
place a real publication time was found, and they are unusable for other
reasons. The **PIT join** column reads "inputs only" where the best available
predicate bounds what information entered a value without establishing that the
value was retrievable before kickoff.

### Canonical Elo recommendation for a future adapter

**Preferred surface: game-level `home_pregame_elo` / `away_pregame_elo`, with
`/ratings/elo` at week *w−1* retained only as an audited fallback.** This
matches what production already does, so the recommendation is to keep the
current preference rather than change it — but the *status* is
`investigate further`, not `implement`.

The evidence for preferring the game-level surface does not rest on the
agreement rates, which prove nothing about timing. It rests on three asymmetries
that survive the hard interpretation rule:

1. **Identifiers.** The game surface carries `game_id` and team IDs; the weekly
   surface carries neither, and 100% of its 12,433 joins went through the name
   fallback (§ 3.3).
2. **Coverage where it matters.** The weekly surface has *zero* coverage at
   regular Week 1 (all 1,492 sides) and *zero* across all postseason groups,
   while the game surface covers 64% of Week 1 sides and 100% of postseason
   sides (§ 3.2).
3. **Effective-time precision.** A game-scoped "pregame" field points at one
   kickoff; a max-week filter points at a range.

Remaining timing gaps, stated explicitly:

- **Neither surface carries a publication timestamp.** This is the single
  blocking gap, and it is why the recommendation is `investigate further`.
- **Revision behavior is uncharacterized** for both surfaces; CFBD guarantees no
  correction schedule.[^cfbd-terms]
- **The weekly `week` parameter is a maximum filter**, not an as-of stamp, and
  our `seasonType=both` request has unspecified postseason behavior (§ 2).
- **Week 0 was never probed.** Ingest requests weeks 1–20, so we cannot say
  whether CFBD would return a preseason row for `week=0`; the observed Week 1
  failure is at least partly an artifact of our own request range.
- **The 2022–2025 divergence is unexplained.** Perfect agreement in 2017–2020
  and ~0.91–0.93 afterward indicates something changed in at least one surface,
  and we cannot attribute it.

Until a publication-time claim can be sourced from CFBD, any Elo feature should
be documented as "provider-labeled pregame, timing unverified" wherever it
appears in schema or model documentation.

## 6. Follow-up adapter branch guidance

Adapter work must not continue on `data/m06-pit-ratings`. After human review of
this memo's recommendations, open a separate branch per approved source, each
with its own design doc, tests, and leakage review:

| Branch | Scope | Entry gate |
|---|---|---|
| `data/m06b-elo-adapter` | Canonical Elo join per § 5; game-level primary, weekly *w−1* audited fallback | Human sign-off on § 5, plus the revision-diff probe and week-0 probe |
| `data/m06c-fpi-weekly-feasibility` | sportsdataverse `cfb_fpi_weekly`: verify the computation-time and PIT-flag fields on one downloaded season, seek any primary source on availability time (§ 4.5 items 2, 8), resolve ESPN↔CFBD crosswalk audit | **Licensing decision resolved first** (§ 4.5 item 4) |
| `data/m06d-core-ratings-probe` | Evaluate `/ratings/core` (`throughWeek` / `modelVersion`) as a new source dossier | Optional; lowest priority |

No branch above is authorized by this memo. Each requires the human review step
the design mandates. If CFBD later adds weekly FPI/SP+ parameters, that must
produce a new memo revision or adapter design — never a silent join change.

## 7. Sources

[^cfbd-ratings-v2]: College Football Data API v2, Ratings reference —
    <https://api.collegefootballdata.com/api/ratings>. Primary source for:
    `/ratings/elo` accepting `year`, `week` ("Week number. Defaults to the
    latest available week in the season."), `seasonType`, `team`, `conference`,
    and returning only `year`, `team`, `conference`, `elo`; `/ratings/fpi`
    accepting `year`, `team`, `conference` with no `week`; `/ratings/sp`
    accepting `year`, `team` with no `week`; `/ratings/core` returning
    `throughWeek`, `throughSeasonType`, `modelVersion`. Retrieved 2026-09-04.

[^cfbd-swagger]: CFBD legacy OpenAPI specification, `swagger.yml` —
    <https://github.com/CFBD/cfb-api/blob/main/swagger.yml>. Primary source
    for: `/ratings/elo` `week` described as "Maximum week filter" and
    `seasonType` as "Maximum season type to consider (defaults to regular if
    week is specified else defaults to postseason)"; `/ratings/sp` parameters
    `year` (`minimum: 1970`) and `team` only; `/ratings/fpi` parameters `year`,
    `team`, `conference` only. Retrieved 2026-09-04.

[^cfbd-python]: CFBD official Python client, `docs/RatingsApi.md` —
    <https://github.com/CFBD/cfbd-python/blob/main/docs/RatingsApi.md>.
    Corroborates the `week` parameter wording on `get_elo`. Retrieved
    2026-09-04.

[^cfbd-terms]: CollegeFootballData.com Terms of Use (Rad Sports Analytics LLC)
    — <https://collegefootballdata.com/terms>. Primary source for: § 4
    permitted private caching/storage/retention and publication of Derived
    Outputs; § 5 prohibition on publishing API Data as a standalone dataset or
    bulk download and on giving third parties programmatic access to stored raw
    responses; § 6 attribution appreciated but not required; § 8 no third-party
    rights granted; § 9 no guarantee of any field, endpoint, correction
    schedule, availability level, or stable identifier. Retrieved 2026-09-04.

[^cfbfastr-fpi]: cfbfastR `load_cfb_fpi_weekly` reference —
    <https://rdrr.io/cran/cfbfastR/man/load_cfb_fpi_weekly.html>; source in
    <https://github.com/sportsdataverse/cfbfastR/blob/main/R/load_cfb_datasets.R>.
    Primary source for the column dictionary quoted in § 4.5:
    `run_date_time_key`, `last_updated`, `snapshot_is_contemporaneous`,
    `snapshot_out_of_sequence`, `team_id`, and coverage from 2005. Retrieved
    2026-09-04.

[^sdv-fpi-release]: sportsdataverse-data release `cfb_fpi_weekly` —
    <https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfb_fpi_weekly>.
    Primary source for: 21 seasons (2005–2025) plus partial 2026, 63 assets,
    18.4 MB; upstream source "CFBD + ESPN"; direct download with no auth or API
    key; assets as plain CSV/Parquet/RDS files on public URLs; bearer token
    required for the `data.sportsdataverse.org` route; existence of the
    `cfb_crosswalk` release. Retrieved 2026-09-04.

[^sdv-license]: `sportsdataverse/sportsdataverse-data` repository license —
    MIT, per the GitHub license API
    (<https://api.github.com/repos/sportsdataverse/sportsdataverse-data/license>),
    file at
    <https://github.com/sportsdataverse/sportsdataverse-data/blob/main/LICENSE>.
    Retrieved 2026-09-04. Note: `sportsdataverse/cfbfastR` reports
    `NOASSERTION` ("Other") for comparison.

[^sdv-ratings-weekly]: sportsdataverse-data release `cfb_ratings_weekly` —
    <https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfb_ratings_weekly>.
    Primary source for: 2004–2025 coverage, long format with `through_week`,
    the inclusive-week leakage warning and the `through_week == W - 1`
    instruction, the ridge-refit description, and the 97.0% vs 58.7% empirical
    verification. Retrieved 2026-09-04.

[^sdv-ratings]: sportsdataverse-data release `cfb_ratings` —
    <https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfb_ratings>.
    Primary source for the "SP+-style" characterization of the sportsdataverse
    opponent-adjusted ratings family. Retrieved 2026-09-04.

### Leads consulted but not treated as primary

- Weekly SP+ rankings articles by Bill Connelly at ESPN, reproduced with
  bylines and timestamps at
  <https://vcpfootball.com/2023/11/12/college-footballs-week-11-sp-rankings-takeaways/>
  (post-Week 11 2023, "Nov 12, 2023, 12:00 PM ET") and with
  `datePublished` `2023-10-22T15:30:00Z` in syndicated metadata for the Week 8
  2023 installment. Used only to establish that weekly SP+ publication
  timestamps exist; **not** treated as a PIT-safe or licensable archive
  (§ 4.6a).
- cfbfastR package site, dataset family table —
  <https://cfbfastr.sportsdataverse.org/> — for the existence of
  `load_cfb_*_crosswalk()` ID crosswalks.[^cfbfastr-site]

[^cfbfastr-site]: cfbfastR package site — <https://cfbfastr.sportsdataverse.org/>.
    Retrieved 2026-09-04.
