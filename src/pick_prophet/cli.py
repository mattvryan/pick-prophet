from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .evaluation.analyze import analyze_file
from .features.build import build_rows, merge_pickem, write_dataset
from .ingest.cfbd import ingest_season
from .weekly.recommend import recommend
from .weekly.signals import fetch_signals_snapshot
from .weekly.validate import validate_slate


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

    weekly = commands.add_parser("weekly", help="weekly Pick'em operations")
    weekly_commands = weekly.add_subparsers(dest="weekly_command", required=True)

    validate = weekly_commands.add_parser(
        "validate-slate", help="validate a captured ESPN slate CSV"
    )
    validate.add_argument("path", type=Path)
    validate.add_argument(
        "--as-of",
        help="optional ISO-8601 timestamp; errors if after any game lock",
    )

    recommend_cmd = weekly_commands.add_parser(
        "recommend", help="emit market-baseline recommendations"
    )
    recommend_cmd.add_argument("--slate", type=Path, required=True)
    recommend_cmd.add_argument("--as-of", required=True)
    recommend_cmd.add_argument("--output-dir", type=Path)

    fetch_signals = weekly_commands.add_parser(
        "fetch-signals", help="capture ratings, rankings, and venue context"
    )
    fetch_signals.add_argument("--slate", type=Path, required=True)
    fetch_signals.add_argument("--snapshot")

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
    elif args.command == "weekly":
        if args.weekly_command == "validate-slate":
            result = validate_slate(args.path, as_of=args.as_of)
            for warning in result.warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            for error in result.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            if result.ok:
                print(f"slate ok: {len(result.rows)} games")
            else:
                print(f"slate invalid: {len(result.errors)} error(s)", file=sys.stderr)
                raise SystemExit(1)
        elif args.weekly_command == "recommend":
            try:
                artifacts = recommend(
                    args.slate,
                    as_of=args.as_of,
                    output_dir=args.output_dir,
                )
            except (ValueError, FileExistsError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
            print(artifacts["output_dir"])
            print(artifacts["recommendations"])
            print(artifacts["card"])
            print(artifacts["run_manifest"])
        elif args.weekly_command == "fetch-signals":
            try:
                print(fetch_signals_snapshot(args.slate, snapshot=args.snapshot))
            except (ValueError, FileExistsError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
