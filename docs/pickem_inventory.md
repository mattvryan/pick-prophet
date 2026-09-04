# ESPN Pick'em historical inventory checklist

Status: **M05 registry tooling ready**; no historical archives ingested yet.
Do not invent slate membership from rankings, TV, or matchup prominence.

Use this checklist while searching personal and public archives. Fill the
results table as items are found or ruled out. Confirmed rows must use the
import contract in `data/external/pickem_slate_TEMPLATE.csv` and pass
`pick-prophet pickem validate-import` with two distinct verifiers.

## Search checklist

- [ ] Personal ESPN Pick'em exports / league history downloads
- [ ] Local screenshots of weekly contest pages (filename + date + sha256)
- [ ] Browser network captures / HAR files from contest loads
- [ ] Pool email threads with weekly slates or reminder lists
- [ ] Shared drive / chat attachments from prior seasons
- [ ] Internet Archive / Wayback Machine snapshots of contest URLs
- [ ] Second-person recollection notes (not sufficient alone for `confirmed`)

## Forward capture (in place)

Weekly operations already capture current slates under `weekly/YYYY-WNN/`.
Convert a weekly slate into template-shaped rows with:

```bash
pick-prophet pickem from-slate weekly/2026-W01/slate.csv \
  --output data/external/pickem_2026_w01_from_slate.csv
```

Then dual-verify, set `source_sha256`, and only then
`verification_status=confirmed`.

Build the sampling-frame registry from one or more validated imports:

```bash
pick-prophet pickem build-registry data/external/pickem_*.csv \
  --known-games data/processed/games_2025.csv \
  --output-dir data/external/pickem_registry
```

Fallback/name matches are written to `pickem_fallback_review.csv` and never
enter `verified_espn_pickem`.

## Inventory results

| Season | Week | Source type | Location / URL | Captured at | Verifiers | Status | Notes |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 2024 | 3 | Dated third-party article | RotoBaller candidate (see M15 inventory) | 2024-09-11 | one source | candidate only | Not imported; requires independent verification and canonical IDs |
| 2024 | 12 | Dated third-party article | RotoBaller candidate (see M15 inventory) | 2024-11-14 | one source | candidate only | Not imported; requires independent verification and canonical IDs |

Leave cells blank until a real artifact exists. Empty rows are intentional.

## Unrecoverable / unsearched weeks

Generate a machine-readable gap list for research seasons 2017–2025:

```bash
pick-prophet pickem inventory-gaps \
  --output docs/pickem_unrecoverable_weeks.json
```

Optional `--recovered PATH` accepts a CSV of `{season,week}` already found.
Absence of evidence does **not** invent slate membership; it only tracks search
coverage.

## Evaluation labeling

- **`all_fbs`**: every FBS-involved game in the processed season table (provisional).
- **`verified_espn_pickem`**: only registry rows with `match_status=exact_id`,
  `is_pickem_game=true`, and `verification_status=confirmed`.

Keep those frames separate in analysis reports; never blend them silently.
`pick-prophet evaluate` stamps `sampling_frame` on every prediction row.
