# Pick Prophet

Reproducible research tooling for ESPN College Pick'em. The project tests whether
pre-game signals improve on the betting market rather than assigning subjective
weights to correlated inputs.

## Milestone 1

The first implementation builds a 2025 FBS candidate-game dataset from
[CollegeFootballData (CFBD)](https://api.collegefootballdata.com/getting-started),
with point-in-time joins for betting lines, polls, and ratings. It also includes:

- a documented, versioned schema;
- immutable raw API snapshots plus provenance metadata;
- leakage-safe feature construction (only information available before kickoff);
- walk-forward evaluation of Vegas and rating baselines;
- an explicit path for importing the exact ESPN Pick'em slate;
- unit tests for the transformations most likely to introduce hindsight bias.

The exact historical ESPN Pick'em slate and public-pick percentages are not
available through a documented historical API. Until an archive is obtained,
`is_pickem_game` is nullable and the dataset is a candidate universe, not a claim
that every FBS game appeared in the contest. See [data sources](docs/data_sources.md).

## Quick start

Requires Python 3.11+ and a free CFBD API key.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export CFBD_API_KEY='...'
pick-prophet ingest --season 2025
pick-prophet build --season 2025
pick-prophet analyze --input data/processed/games_2025.csv
pytest
```

`ingest` writes timestamped JSON under `data/raw/cfbd/`. Re-running it does not
silently overwrite a snapshot. `build` creates `data/processed/games_2025.csv`
and a companion data-quality report. Use `--snapshot <timestamp>` to reproduce a
specific run.

## Repository layout

```text
data/{raw,processed,external}/
docs/
notebooks/
src/pick_prophet/{ingest,features,models,evaluation}/
tests/
weekly/
```

## Research rules

1. A feature's timestamp must precede kickoff.
2. Closing-market fields are evaluated as their own benchmark. Models intended
   for earlier lock times must use odds captured at that lock time instead.
3. Seasons are held out chronologically; random train/test splits are prohibited.
4. Accuracy is secondary to log loss, Brier score, and calibration.
5. Missingness is preserved and reported. It is never silently converted to a
   rank, rating, or pick.

See [methodology](docs/methodology.md) and [schema](docs/schema.md) for details.
The prioritized build, research, and weekly-operation queue lives in the
[execution plan](docs/implementation_plan.md).
