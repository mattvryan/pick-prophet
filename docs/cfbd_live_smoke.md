# CFBD live smoke tests (manual)

These checks are **not** part of CI. Automated ingest tests use fixtures and a
fake client only (`tests/test_cfbd_ingest.py`).

## Prerequisites

- Local `.env` with `CFBD_API_KEY` (never commit the key)
- Network access to `https://api.collegefootballdata.com`
- Writable `data/raw/` (gitignored)

## Smoke checklist

1. Targeted week capture does not pull unused weeks:

```bash
pick-prophet ingest --season 2025 --weeks 1 --snapshot smoke-w1
```

Confirm `manifest.json` lists `request.weeks: [1]` and only Elo week 1 was
needed for the weekly endpoint.

2. Resume leaves completed endpoint files untouched:

```bash
# After interrupting or deleting one endpoint file, e.g. elo.json:
pick-prophet ingest --season 2025 --weeks 1 --snapshot smoke-w1 --resume
```

Completed `games.json` / `lines.json` hashes should match the prior manifest
entries.

3. Re-running without `--resume` must fail without overwrite:

```bash
pick-prophet ingest --season 2025 --weeks 1 --snapshot smoke-w1
# expect: FileExistsError / snapshot already exists
```

4. Schema drift preserves `*.bad.json` and fails loudly (simulate only in a
dev fork by temporarily tightening `ENDPOINT_REQUIRED_FIELDS`).

5. Build still works against an existing 2017–2025 snapshot:

```bash
pick-prophet build --season 2025
# expect games_2025.csv plus games_2025.name_join_audit.csv
```

Record pass/fail locally; do not commit raw smoke snapshots.
