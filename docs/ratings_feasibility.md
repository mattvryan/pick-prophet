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

Two corollaries are applied throughout this memo:

1. **Absence of a documented restriction is not permission.** Where licensing
   terms are silent or ambiguous, the source is labeled `unknown`, not
   `permitted`.
2. **Unresolved facts are labeled.** Claims are tagged `inference` where they
   are our reasoning rather than a publisher statement, and `unknown` where no
   primary source could be found. Everything else cites a primary source.

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
   resolution. *Publication time*: absent. *Retrieval time*: ours only. A pull
   made after a season necessarily reflects end-of-season information.
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
7. **Revision behavior.** A season-level rating retrieved today *is* the
   post-season revision. There is no mechanism to recover the value as it stood
   in week *w*.
8. **Join-before-kickoff.** **No.** There is no observation whose effective or
   publication time can be placed before a mid-season `kickoff_utc`. Joining
   this to a week-*w* game injects end-of-season information — exactly the
   leakage the existing `build.py` comment guards against.
9. **Recommendation: `omit`.** Not a close call. The public CFBD FPI endpoint
   has no week parameter, so there is nothing to make PIT-safe; the only
   available observation embeds the full season's results. It must stay raw-only
   and unjoined. This is a statement about *this endpoint*, not about FPI as a
   metric — see § 4.4 for the weekly FPI route.

### 4.4 CFBD SP+ (`/ratings/sp`)

1. **Availability.** **Season-level only.** The v2 reference lists `year` and
   `team` and **no `week`**;[^cfbd-ratings-v2] the legacy swagger shows the same
   two parameters plus `minimum: 1970`.[^cfbd-swagger] One row per team per
   season.
2. **Temporal fields.** *Effective time*: the season. *Publication time*:
   absent. *Retrieval time*: ours only. Same end-of-season contamination as FPI.
3. **Retrieval.** `GET /ratings/sp?year={season}`, ingested as `sp.json` and
   retained raw-only (`Endpoint("sp", "/ratings/sp")`).
4. **Licensing / redistribution.** Same CFBD Terms.[^cfbd-terms] SP+ is Bill
   Connelly's system, published at ESPN; no third-party rights are
   granted,[^cfbd-terms] so republication of SP+ values as data is `unknown`.
5. **Stable identifiers.** Name-keyed (`team`, `conference`); no team
   ID.[^cfbd-ratings-v2]
6. **Coverage.** Season-level FBS coverage back to 1970 per the swagger
   minimum,[^cfbd-swagger] but again irrelevant given the temporal defect.
7. **Revision behavior.** As with FPI, today's value is the final revision;
   in-season states are unrecoverable from this endpoint.
8. **Join-before-kickoff.** **No**, for the same reason as § 4.3.
9. **Recommendation: `omit`.** Identical reasoning to FPI. Keep raw-only and
   unjoined.

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
   This fully spans our 2017–2025 research window.
2. **Temporal fields.** **This is the only in-scope source with explicit
   as-of metadata**, and the distinctions are documented precisely:
   - `run_date_time_key` — "ESPN's run key for the snapshot, as an integer
     timestamp (e.g. 20241021040000). This is the AS-OF date the snapshot
     represents, which is not the same as `last_updated` (when ESPN computed
     it)".[^cfbfastr-fpi] → *effective time*.
   - `last_updated` — when ESPN computed the snapshot.[^cfbfastr-fpi] →
     *publication/computation time*.
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

   The publisher therefore not only exposes both timestamps but names the exact
   leakage trap and instructs consumers to filter it.
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
7. **Revision behavior.** **Documented, and the most honest of any source
   reviewed.** ESPN overwrites the week-1 slot with a late-season computation
   (2024 week 1 is stamped 2024-12-15), and pre-2015 rows are a single
   retrospective pass.[^cfbfastr-fpi] Both conditions are flagged per row rather
   than left for the consumer to discover.
8. **Join-before-kickoff.** **Yes, in principle — the only source reviewed for
   which this is true.** An adapter can filter to
   `snapshot_is_contemporaneous == True` and `snapshot_out_of_sequence == False`,
   then select the latest row whose `last_updated` (computation time) is strictly
   before `kickoff_utc`. Because both an as-of key and a computation timestamp
   are present, the strict-inequality predicate the design asks for is actually
   expressible instead of assumed.
9. **Recommendation: `investigate further`.** On temporal semantics this is the
   strongest candidate in the memo and the only one that could support a
   genuinely defensible PIT claim. It is held back by two unresolved
   non-technical questions, not by data quality: (a) the redistribution
   question in item 4, which needs a human decision on whether ESPN-derived
   weekly FPI may be stored and whether derived features may be committed; and
   (b) the ESPN↔CFBD team-ID crosswalk in item 5, which introduces a second
   join needing its own audit trail. A follow-up should also verify the
   timestamp fields empirically on one downloaded season before any adapter is
   designed, since every claim in items 2 and 7 is currently documentation-based
   rather than observed.

### 4.6 Credible weekly SP+ archive

Searching for a PIT-safe weekly SP+ source produced two candidate families,
and **neither is usable as a point-in-time archive**.

**(a) ESPN weekly SP+ articles (Bill Connelly).** SP+ rankings are genuinely
published weekly with per-article timestamps — for example the post-Week 11
2023 rankings are bylined "Bill Connelly, ESPN Staff Writer Nov 12, 2023,
12:00 PM ET" and carry a full ratings table, and the Week 8 2023 installment
carries `datePublished` `2023-10-22T15:30:00Z` in its syndicated metadata. So
publication timestamps *exist* at article granularity. But:

- *Retrieval* would mean scraping ESPN Insider article bodies. The content is
  paywalled, HTML-formatted, and has no stable machine-readable endpoint.
- *Licensing* is the harder problem: ESPN article content is not ours to
  redistribute, and CFBD's Terms grant no third-party rights.[^cfbd-terms]
  `unknown` at best, and realistically prohibited.
- *Identifiers* are display team names inside prose tables, with no IDs.
- *Coverage* across 2017–2025 for every week would require locating and parsing
  well over a hundred paywalled articles, with no guarantee of a complete set.

**(b) `cfb_ratings_weekly` (sportsdataverse).** This release does provide weekly
opponent-adjusted team ratings for 2004–2025 in long format with a
`through_week` column.[^sdv-ratings-weekly] Two facts disqualify it as *SP+*
and complicate it as a PIT source:

- It is **not Bill Connelly's SP+**. The related `cfb_ratings` release describes
  the family as "SP+-**style**" opponent-adjusted ratings built by
  sportsdataverse over released play-by-play — a different system that happens
  to resemble SP+.[^sdv-ratings] Treating it as SP+ would misattribute the
  metric.
- Its as-of semantics are a **retrospective refit**, and the publisher is
  admirably explicit about the trap: "`through_week == W` is **inclusive of
  week W**: the snapshot contains games PLAYED in week W. To project week W, use
  the `through_week == W - 1` row. Filtering `through_week == W` and predicting
  week W leaks that week's results." They verified this empirically against 2024
  data: 97.0% consistent with the inclusive reading versus 58.7% with the
  exclusive one.[^sdv-ratings-weekly] `inference`: because "the ridge is refit
  on everything up to week W",[^sdv-ratings-weekly] a `through_week == W - 1`
  row is *input*-PIT-safe (no future game results enter the fit) even though it
  was computed retrospectively and therefore has no contemporaneous publication
  time.

**Recommendation: `omit`** for weekly SP+ specifically. No credible,
reproducible, license-clear weekly SP+ archive with as-of timestamps was
identified. The ESPN articles have timestamps but are unscrapable and
unlicensable; `cfb_ratings_weekly` is license-clearer and PIT-tractable but is a
different metric and must not be labeled SP+. If a future PR wants an
opponent-adjusted weekly rating, it should evaluate `cfb_ratings_weekly` **on
its own terms and under its own name**, using the `through_week == W - 1` rule,
as a new source dossier — not as a stand-in for SP+.

## 5. Recommendation table

| Source | Weekly granularity | Publication timestamp | Stable ID | PIT join possible | Recommendation |
|---|---|---|---|---|---|
| CFBD game pregame Elo (`/games`) | Per game (better than weekly) | **No** | **Yes** (`game_id`, team IDs) | Game-scoped but unproven | `investigate further` |
| CFBD weekly Elo (`/ratings/elo`) | Yes (max-week filter) | No | **No** (name only) | Approximate; no Wk 1 / postseason | `investigate further` (fallback only) |
| CFBD FPI (`/ratings/fpi`) | **No** (season only) | No | No | **No** | `omit` |
| CFBD SP+ (`/ratings/sp`) | **No** (season only) | No | No | **No** | `omit` |
| sportsdataverse weekly FPI (`cfb_fpi_weekly`) | Yes | **Yes** (`last_updated` + as-of key + PIT flags) | Yes (ESPN `team_id`; needs crosswalk) | **Yes, in principle** | `investigate further` |
| Weekly SP+ (ESPN articles / other archives) | Yes | Yes, but paywalled prose | No | Not licensably | `omit` |

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
| `data/m06c-fpi-weekly-feasibility` | sportsdataverse `cfb_fpi_weekly`: verify timestamp fields on one downloaded season, resolve ESPN↔CFBD crosswalk audit | **Licensing decision resolved first** (§ 4.5 item 4) |
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
