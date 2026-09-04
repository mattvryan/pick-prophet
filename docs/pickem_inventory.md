# ESPN Pick'em historical inventory checklist

Status: tooling ready; **no historical archives ingested yet**. Do not invent
slate membership from rankings, TV, or matchup prominence.

Use this checklist while searching personal and public archives. Fill the
results table as items are found or ruled out. Confirmed rows must use the
import contract in `data/external/pickem_slate_TEMPLATE.csv` and pass
`pick-prophet pickem validate-import` with two distinct verifiers.

## Search checklist

- [ ] Personal ESPN Pick'em exports / league history downloads
- [ ] Local screenshots of weekly contest pages (filename + date)
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

Then dual-verify before setting `verification_status=confirmed`.

## Inventory results

| Season | Week | Source type | Location / URL | Captured at | Verifiers | Status | Notes |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

Leave cells blank until a real artifact exists. Empty rows are intentional.

## Evaluation labeling

- **all-FBS**: every FBS-involved game in the processed season table (provisional).
- **confirmed Pick'em**: only rows with `is_pickem_game=true` and
  `verification_status=confirmed` after dual verification.

Keep those frames separate in analysis reports; never blend them silently.
