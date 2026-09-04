from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .evaluation.analyze import analyze_file
from .evaluation.early_season import analyze_early_season
from .evaluation.evaluate import evaluate
from .features.build import build_rows, merge_pickem, write_dataset
from .features.coverage import run_coverage
from .features.matrix import build_and_write, parse_seasons_arg
from .features.pickem import (
    import_pickem_file,
    load_known_game_ids,
    slate_to_template_rows,
    validate_pickem_import,
    write_template_csv,
)
from .features.pickem_registry import (
    build_registry,
    unrecoverable_weeks_report,
    write_registry,
)
from .ingest.cfbd import ingest_season
from .models.residual_ablation import run_ablation
from .models.residual_diagnostics import diagnose_residual
from .models.residual_fit import fit_residual_walkforward
from .weekly.grade import grade_week
from .weekly.recommend import recommend
from .weekly.results import fetch_results
from .weekly.signals import fetch_signals_snapshot
from .weekly.submission import record_submission
from .weekly.tiebreaker import recommend_tiebreaker
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
    ingest.add_argument(
        "--weeks",
        type=str,
        help="comma-separated weeks for weekly endpoints (e.g. 1,2,3)",
    )
    ingest.add_argument(
        "--snapshot",
        help="snapshot directory name; required with --resume",
    )
    ingest.add_argument(
        "--resume",
        action="store_true",
        help="resume an incomplete snapshot without overwriting completed files",
    )

    build = commands.add_parser("build", help="build the canonical game table")
    build.add_argument("--season", type=int, required=True)
    build.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    build.add_argument("--snapshot")
    build.add_argument("--pickem-csv", type=Path)
    build.add_argument("--output", type=Path)

    analyze = commands.add_parser("analyze", help="score baselines walk-forward")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--output", type=Path)

    early = commands.add_parser(
        "analyze-early-season", help="run paired early-season walk-forward tests"
    )
    early.add_argument("--input", type=Path, required=True)
    early.add_argument("--output-dir", type=Path)

    evaluate_cmd = commands.add_parser(
        "evaluate", help="run protocol-stamped walk-forward evaluation"
    )
    evaluate_cmd.add_argument("--input", type=Path, required=True)
    evaluate_cmd.add_argument("--output-dir", type=Path)
    evaluate_cmd.add_argument(
        "--protocol",
        default="1.0.0",
        help="evaluation protocol version (default: 1.0.0)",
    )

    matrix_cmd = commands.add_parser(
        "matrix",
        help="build the leakage-safe M07 modeling feature matrix",
    )
    matrix_cmd.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/processed"),
        help="directory containing games_{season}.csv",
    )
    matrix_cmd.add_argument(
        "--seasons",
        required=True,
        help="comma seasons and/or ranges, e.g. 2017-2025 or 2018,2020",
    )
    matrix_cmd.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/matrix"),
    )

    residual = commands.add_parser(
        "fit-residual",
        help="fit M08 market-residual logistic variants on a matrix",
    )
    residual.add_argument("--matrix", type=Path, required=True)
    residual.add_argument("--protocol", default="1.0.0")
    residual.add_argument("--matrix-schema", default="1.0.0")
    residual.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/residual"),
    )

    diagnose = commands.add_parser(
        "diagnose-residual",
        help="M09 inference/calibration diagnostics on raw residual predictions",
    )
    diagnose.add_argument("--predictions-dir", type=Path, required=True)
    diagnose.add_argument("--matrix", type=Path, required=True)
    diagnose.add_argument("--protocol", default="1.0.0")
    diagnose.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/residual_diagnostics/run"),
    )

    ablate = commands.add_parser(
        "ablate-residual",
        help="M10 feature ablation and robustness over residual stack",
    )
    ablate.add_argument("--matrix", type=Path, required=True)
    ablate.add_argument("--protocol", default="1.0.0")
    ablate.add_argument("--matrix-schema", default="1.0.0")
    ablate.add_argument(
        "--out-dir",
        type=Path,
        default=Path("artifacts/residual_ablation/run"),
    )
    ablate.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help="optional path for incremental_value_report.md",
    )

    coverage = commands.add_parser(
        "coverage", help="audit processed season CSVs and write coverage report"
    )
    coverage.add_argument(
        "--processed-root", type=Path, default=Path("data/processed")
    )
    coverage.add_argument(
        "--report",
        type=Path,
        default=Path("docs/data_coverage_report.md"),
    )
    coverage.add_argument(
        "--no-write-quality",
        action="store_true",
        help="skip rewriting per-season .quality.json files",
    )
    coverage.add_argument(
        "--summary-json",
        type=Path,
        default=Path("docs/coverage_summary.json"),
        help="machine-readable cross-season coverage summary",
    )
    coverage.add_argument(
        "--week-csv",
        type=Path,
        default=Path("docs/coverage_by_week.csv"),
        help="per season/week coverage table",
    )
    coverage.add_argument(
        "--windows-json",
        type=Path,
        default=Path("docs/coverage_evaluation_windows.json"),
        help="recommended evaluation windows by source",
    )
    coverage.add_argument(
        "--no-machine-readable",
        action="store_true",
        help="skip JSON/CSV coverage exports",
    )

    pickem = commands.add_parser("pickem", help="ESPN Pick'em import tooling")
    pickem_commands = pickem.add_subparsers(dest="pickem_command", required=True)

    validate_import = pickem_commands.add_parser(
        "validate-import", help="validate a template-shaped Pick'em CSV"
    )
    validate_import.add_argument("path", type=Path)
    validate_import.add_argument(
        "--known-games",
        type=Path,
        help="optional processed games CSV used only to warn on unmatched IDs",
    )

    import_cmd = pickem_commands.add_parser(
        "import",
        help="validate then copy into data/external/ without overwriting",
    )
    import_cmd.add_argument("path", type=Path)
    import_cmd.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="target path under data/external/",
    )
    import_cmd.add_argument("--known-games", type=Path)

    from_slate = pickem_commands.add_parser(
        "from-slate",
        help="convert weekly slate.csv into template rows (forward capture)",
    )
    from_slate.add_argument("path", type=Path)
    from_slate.add_argument("--output", type=Path, required=True)

    build_registry_cmd = pickem_commands.add_parser(
        "build-registry",
        help="merge validated imports into a verified sampling-frame registry",
    )
    build_registry_cmd.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="one or more validated Pick'em import CSVs",
    )
    build_registry_cmd.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/external/pickem_registry"),
    )
    build_registry_cmd.add_argument("--known-games", type=Path)

    inventory_cmd = pickem_commands.add_parser(
        "inventory-gaps",
        help="list research weeks without recovered registry evidence",
    )
    inventory_cmd.add_argument(
        "--recovered",
        type=Path,
        help="optional CSV with season,week columns already recovered",
    )
    inventory_cmd.add_argument(
        "--output",
        type=Path,
        default=Path("docs/pickem_unrecoverable_weeks.json"),
    )

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
    recommend_cmd.add_argument("--market", type=Path)
    recommend_cmd.add_argument("--as-of", required=True)
    recommend_cmd.add_argument("--output-dir", type=Path)

    fetch_signals = weekly_commands.add_parser(
        "fetch-signals", help="capture ratings, rankings, and venue context"
    )
    fetch_signals.add_argument("--slate", type=Path, required=True)
    fetch_signals.add_argument("--snapshot")

    tiebreaker = weekly_commands.add_parser(
        "tiebreaker", help="recommend a whole-number total for the designated game"
    )
    tiebreaker.add_argument("--slate", type=Path, required=True)
    tiebreaker.add_argument("--market", type=Path, required=True)
    tiebreaker.add_argument("--game-id", required=True)
    tiebreaker.add_argument("--as-of", required=True)
    tiebreaker.add_argument("--output-dir", type=Path, required=True)

    record = weekly_commands.add_parser(
        "record-submission",
        help="record immutable confirmation of an ESPN Pick'em submission",
    )
    record.add_argument("--week-dir", type=Path, required=True)
    record.add_argument("--submitted-at", required=True)
    record.add_argument("--tiebreaker", type=int, required=True)
    record.add_argument("--operator")
    record.add_argument("--final-picks", type=Path)
    record.add_argument(
        "--submitted-picks",
        type=Path,
        help="optional CSV of what was entered if it differs from final_picks.csv",
    )
    record.add_argument("--confirmation-file", type=Path)
    record.add_argument("--confirmation-sha256")
    record.add_argument("--notes")
    record.add_argument(
        "--output",
        type=Path,
        help="defaults to week-dir/submission.json; use a new path for revisions",
    )

    fetch_results_cmd = weekly_commands.add_parser(
        "fetch-results", help="capture completed CFBD scores for a weekly slate"
    )
    fetch_results_cmd.add_argument("--week-dir", type=Path, required=True)
    fetch_results_cmd.add_argument("--slate", type=Path)
    fetch_results_cmd.add_argument("--snapshot")
    fetch_results_cmd.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="write a snapshot even if some games are unfinished",
    )

    grade_cmd = weekly_commands.add_parser(
        "grade", help="grade a submitted weekly card against final results"
    )
    grade_cmd.add_argument("--week-dir", type=Path, required=True)
    grade_cmd.add_argument("--results", type=Path, required=True)
    grade_cmd.add_argument("--submission", type=Path)
    grade_cmd.add_argument("--recommendations", type=Path)
    grade_cmd.add_argument("--tiebreaker-json", type=Path)
    grade_cmd.add_argument("--output-dir", type=Path)

    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "ingest":
        weeks = None
        if getattr(args, "weeks", None):
            weeks = [int(part.strip()) for part in args.weeks.split(",") if part.strip()]
        print(
            ingest_season(
                args.season,
                args.raw_root,
                max_week=args.max_week,
                weeks=weeks,
                snapshot=args.snapshot,
                resume=args.resume,
            )
        )
    elif args.command == "build":
        snapshot = (
            args.raw_root / "cfbd" / str(args.season) / args.snapshot
            if args.snapshot
            else _latest_snapshot(args.raw_root, args.season)
        )
        rows = build_rows(snapshot)
        if args.pickem_csv:
            merge_pickem(rows.rows, args.pickem_csv)
        output = args.output or Path(f"data/processed/games_{args.season}.csv")
        report = write_dataset(
            rows.rows, output, name_join_audit=rows.name_join_audit
        )
        print(f"wrote {output} and {report}")
        audit_path = output.with_name(output.stem + ".name_join_audit.csv")
        if audit_path.exists():
            print(audit_path)
    elif args.command == "analyze":
        print(analyze_file(args.input, args.output))
    elif args.command == "analyze-early-season":
        artifacts = analyze_early_season(args.input, args.output_dir)
        print(artifacts["summary"])
        print(artifacts["predictions"])
    elif args.command == "evaluate":
        try:
            artifacts = evaluate(
                args.input,
                args.output_dir,
                protocol_version=args.protocol,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(artifacts["summary"])
        print(artifacts["predictions"])
    elif args.command == "matrix":
        seasons = parse_seasons_arg(args.seasons)
        result = build_and_write(
            input_dir=args.input_dir,
            seasons=seasons,
            output_dir=args.output_dir,
        )
        print(args.output_dir / "games_matrix_v1.csv")
        print(args.output_dir / "matrix_manifest.json")
        print(
            f"retained={len(result.rows)} excluded={len(result.exclusions)} "
            f"input={result.input_rows}"
        )
    elif args.command == "fit-residual":
        summary = fit_residual_walkforward(
            args.matrix,
            args.output_dir,
            protocol_version=args.protocol,
            matrix_schema_version=args.matrix_schema,
        )
        print(args.output_dir / "predictions.csv")
        print(args.output_dir / "summary.json")
        print(f"folds={len(summary.get('folds', []))}")
    elif args.command == "diagnose-residual":
        try:
            artifacts = diagnose_residual(
                args.predictions_dir,
                args.matrix,
                args.out_dir,
                protocol_version=args.protocol,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(artifacts["summary"])
        print(artifacts["report"])
    elif args.command == "ablate-residual":
        try:
            artifacts = run_ablation(
                args.matrix,
                args.out_dir,
                protocol_version=args.protocol,
                matrix_schema_version=args.matrix_schema,
                write_report_path=args.write_report,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(artifacts["decision_worksheet"])
        print(artifacts["report"])
    elif args.command == "coverage":
        kwargs = {
            "report_path": args.report,
            "write_quality": not args.no_write_quality,
        }
        if not args.no_machine_readable:
            kwargs.update(
                {
                    "summary_json": args.summary_json,
                    "week_csv": args.week_csv,
                    "windows_json": args.windows_json,
                }
            )
        audits, _markdown = run_coverage(args.processed_root, **kwargs)
        for audit in sorted(audits, key=lambda a: a.season):
            print(f"{audit.season}: {audit.status} ({audit.rows} rows)")
        print(args.report)
        if not args.no_machine_readable:
            print(args.summary_json)
            print(args.week_csv)
            print(args.windows_json)
        if any(a.status == "fail" for a in audits) or not audits:
            raise SystemExit(1)
    elif args.command == "pickem":
        known = None
        if getattr(args, "known_games", None):
            known = load_known_game_ids(args.known_games)
        if args.pickem_command == "validate-import":
            result = validate_pickem_import(args.path, known_game_ids=known)
            for warning in result.warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            for error in result.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            if result.ok:
                print(f"import ok: {len(result.rows)} rows")
            else:
                print(
                    f"import invalid: {len(result.errors)} error(s)",
                    file=sys.stderr,
                )
                raise SystemExit(1)
        elif args.pickem_command == "import":
            try:
                result = validate_pickem_import(args.path, known_game_ids=known)
                for warning in result.warnings:
                    print(f"WARNING: {warning}", file=sys.stderr)
                dest = import_pickem_file(
                    args.path, args.destination, known_game_ids=known
                )
            except (ValueError, FileExistsError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
            print(dest)
        elif args.pickem_command == "from-slate":
            try:
                rows = slate_to_template_rows(args.path)
                print(write_template_csv(rows, args.output))
            except (ValueError, OSError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
        elif args.pickem_command == "build-registry":
            known = None
            if args.known_games:
                known = load_known_game_ids(args.known_games)
            registry = build_registry(list(args.paths), known_game_ids=known)
            for warning in registry.warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            for error in registry.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            if not registry.ok:
                raise SystemExit(1)
            artifacts = write_registry(registry, args.output_dir)
            for path in artifacts.values():
                print(path)
        elif args.pickem_command == "inventory-gaps":
            recovered: set[tuple[int, int]] = set()
            if args.recovered and args.recovered.exists():
                with args.recovered.open(newline="") as handle:
                    for row in csv.DictReader(handle):
                        recovered.add((int(row["season"]), int(row["week"])))
            report = unrecoverable_weeks_report(
                research_seasons=list(range(2017, 2026)),
                recovered=recovered,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print(args.output)
            print(
                "unrecoverable_or_unsearched="
                f"{len(report['unrecoverable_or_unsearched_season_weeks'])}"
            )
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
                    market_path=args.market,
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
        elif args.weekly_command == "tiebreaker":
            try:
                artifacts = recommend_tiebreaker(
                    args.slate,
                    args.market,
                    game_id=args.game_id,
                    as_of=args.as_of,
                    output_dir=args.output_dir,
                )
            except (ValueError, FileExistsError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
            print(artifacts["json"])
            print(artifacts["card"])
        elif args.weekly_command == "record-submission":
            try:
                print(
                    record_submission(
                        week_dir=args.week_dir,
                        submitted_at=args.submitted_at,
                        tiebreaker_total=args.tiebreaker,
                        operator=args.operator,
                        final_picks=args.final_picks,
                        submitted_picks=args.submitted_picks,
                        confirmation_file=args.confirmation_file,
                        confirmation_sha256=args.confirmation_sha256,
                        notes=args.notes,
                        output_path=args.output,
                    )
                )
            except (ValueError, FileExistsError, FileNotFoundError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
        elif args.weekly_command == "fetch-results":
            try:
                print(
                    fetch_results(
                        week_dir=args.week_dir,
                        slate_path=args.slate,
                        snapshot=args.snapshot,
                        allow_incomplete=args.allow_incomplete,
                    )
                )
            except (ValueError, FileExistsError, FileNotFoundError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
        elif args.weekly_command == "grade":
            try:
                artifacts = grade_week(
                    week_dir=args.week_dir,
                    results_path=args.results,
                    submission_path=args.submission,
                    recommendations_path=args.recommendations,
                    tiebreaker_path=args.tiebreaker_json,
                    output_dir=args.output_dir,
                )
            except (ValueError, FileExistsError, FileNotFoundError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
            print(artifacts["output_dir"])
            print(artifacts["json"])
            print(artifacts["markdown"])


if __name__ == "__main__":
    main()
