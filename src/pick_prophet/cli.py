from __future__ import annotations

import argparse
from pathlib import Path

from .evaluation.analyze import analyze_file
from .features.build import build_rows, merge_pickem, write_dataset
from .ingest.cfbd import ingest_season


def _latest_snapshot(raw_root: Path, season: int) -> Path:
    candidates = sorted((raw_root / "cfbd" / str(season)).glob("*/manifest.json"))
    if not candidates:
        raise FileNotFoundError(f"no snapshot for {season}; run ingest first")
    return candidates[-1].parent


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="pick-prophet")
    commands = root.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="download an immutable CFBD snapshot")
    ingest.add_argument("--season", type=int, required=True)
    ingest.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    ingest.add_argument("--max-week", type=int, default=20)
    build = commands.add_parser("build", help="build the canonical game table")
    build.add_argument("--season", type=int, required=True)
    build.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    build.add_argument("--snapshot")
    build.add_argument("--pickem-csv", type=Path)
    build.add_argument("--output", type=Path)
    analyze = commands.add_parser("analyze", help="score baselines walk-forward")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--output", type=Path)
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "ingest":
        print(ingest_season(args.season, args.raw_root, max_week=args.max_week))
    elif args.command == "build":
        snapshot = (
            args.raw_root / "cfbd" / str(args.season) / args.snapshot
            if args.snapshot
            else _latest_snapshot(args.raw_root, args.season)
        )
        rows = build_rows(snapshot)
        if args.pickem_csv:
            merge_pickem(rows, args.pickem_csv)
        output = args.output or Path(f"data/processed/games_{args.season}.csv")
        report = write_dataset(rows, output)
        print(f"wrote {output} and {report}")
    elif args.command == "analyze":
        print(analyze_file(args.input, args.output))


if __name__ == "__main__":
    main()
