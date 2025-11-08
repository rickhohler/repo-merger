from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List, Sequence

from .auto import ScanContext, ScanManifest, ScanReportEntry, scan_for_repos
from .fragments import ingest_fragments, write_fragment_manifest
from .handler_registry import HandlerRegistry
from .inspection import FragmentAnalysis, inspect_fragments
from .merge import MergeResult, merge_fragments
from .recovery import recover_fragments
from .reporting import summarize_cli, write_markdown_report
from .unhandled import UnhandledScenarioRegistry
from .workspace import RepoMergerError, derive_identifier, mirror_golden_repo, prepare_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-merger",
        description="Repo Merger helper CLI.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Prepare workspace and execute a mode.")
    _add_run_arguments(run_parser)

    handler_parser = subparsers.add_parser("handlers", help="Manage handler registry.")
    _add_handler_arguments(handler_parser)

    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
        help="Root directory where merged workspaces will be created.",
    )
    parser.add_argument(
        "--golden",
        required=False,
        type=Path,
        help="Path to the authoritative (golden) repository to mirror.",
    )
    parser.add_argument(
        "--fragment",
        dest="fragments",
        action="append",
        default=[],
        type=Path,
        help="Optional fragment repository/directory paths (repeatable).",
    )
    parser.add_argument(
        "--identifier",
        type=str,
        help="Explicit identifier for this merged workspace (otherwise derived).",
    )
    parser.add_argument(
        "--mode",
        choices=["analyze", "merge"],
        default="analyze",
        help="Execution mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Describe the actions without mutating the filesystem.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow existing workspace directories to be replaced.",
    )
    parser.add_argument(
        "--recover-missing",
        action="store_true",
        help="Recover fragments missing git metadata into synthetic repos.",
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        help="Resume merge mode from a specific fragment ID.",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan a directory for golden/fragment repos before executing.",
    )
    parser.add_argument(
        "--scan-source",
        type=Path,
        help="Directory that contains golden/fragment repos for scanning.",
    )
    parser.add_argument(
        "--scan-create-structure",
        action="store_true",
        help="Create the scan-source directory if it does not exist.",
    )
    parser.add_argument(
        "--scan-golden-pattern",
        default="*golden*",
        help="Glob pattern to detect golden repos when scanning.",
    )
    parser.add_argument(
        "--scan-fragment-pattern",
        default="fragment*",
        help="Glob pattern to detect fragment repos when scanning.",
    )


def _add_handler_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    handler_subparsers = parser.add_subparsers(dest="handler_command", required=True)

    add_parser = handler_subparsers.add_parser("add", help="Scaffold a new handler.")
    add_parser.add_argument("name", help="Handler name (slug).")
    add_parser.add_argument("--description", required=True, help="Short handler description.")

    handler_subparsers.add_parser("list", help="List registered handlers.")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def run(args: argparse.Namespace) -> int:
    configure_logging(args.verbose)
    logging.debug("Arguments: %s", args)

    if args.command == "run":
        _run_workspace_flow(args)
        return 0
    if args.command == "handlers":
        _run_handler_flow(args)
        return 0
    raise RepoMergerError(f"Unknown command: {args.command}")


def _run_workspace_flow(args: argparse.Namespace) -> None:
    scenario_registry = UnhandledScenarioRegistry(Path(__file__).resolve().parents[1])
    workspace_root = args.workspace.expanduser().resolve()

    if not args.golden:
        raise RepoMergerError("--golden is required for workspace runs.")

    fragments = args.fragments or []
    _process_single_run(
        args=args,
        workspace_root=workspace_root,
        golden_path=args.golden,
        fragments=fragments,
        identifier_override=args.identifier,
        scenario_registry=scenario_registry,
    )


def _process_single_run(
    args: argparse.Namespace,
    workspace_root: Path,
    golden_path: Path,
    fragments: Sequence[Path],
    identifier_override: str | None,
    scenario_registry: UnhandledScenarioRegistry,
) -> None:
    golden_path = golden_path.expanduser().resolve()
    logging.info("Golden repo: %s", golden_path)
    logging.info("Workspace root: %s", workspace_root)

    identifier = derive_identifier(golden_path, identifier_override)
    logging.info("Workspace identifier: %s", identifier)

    paths = prepare_workspace(
        workspace_root=workspace_root,
        identifier=identifier,
        dry_run=args.dry_run,
        force=args.force,
    )

    fragment_paths = _normalize_fragment_paths(fragments)
    scan_context: ScanContext | None = None

    if args.scan:
        scan_context = _prepare_scan_context(args, paths, golden_path)
        fragment_paths.extend(scan_context.fragments_to_ingest())
        fragment_paths = _normalize_fragment_paths(fragment_paths)

    if args.dry_run:
        logging.info("Dry run enabled; skipping golden mirroring.")
    else:
        mirror_golden_repo(golden_path, paths.golden)

    records = []
    if fragment_paths:
        records = ingest_fragments(fragment_paths, paths, dry_run=args.dry_run)
        logging.info("Processed %d fragment(s)", len(records))
    else:
        logging.info("No fragments provided for ingestion.")

    if args.recover_missing and records:
        recovery_results = recover_fragments(records, paths, dry_run=args.dry_run)
        logging.info("Recovery results: %d fragment(s)", len(recovery_results))
        if not args.dry_run:
            manifest_path = paths.root / "fragments_manifest.json"
            write_fragment_manifest(manifest_path, records)

    analyses = []
    if records:
        analyses = inspect_fragments(
            records,
            paths,
            dry_run=args.dry_run,
            registry=scenario_registry,
        )
        logging.info("Inspection results written for %d fragment(s)", len(analyses))
        if not args.dry_run:
            _emit_report(paths, analyses, merges=None)

    if args.mode == "analyze":
        logging.info("Analyze mode complete for workspace %s", paths.root)
    elif args.mode == "merge":
        merge_results = merge_fragments(
            records,
            paths,
            dry_run=args.dry_run,
            resume_from=args.resume_from,
        )
        logging.info("Merge results: %d fragment(s)", len(merge_results))
        if not args.dry_run:
            _emit_report(paths, analyses, merges=merge_results)
    else:
        raise RepoMergerError(f"Unsupported mode requested: {args.mode}")

    if scan_context is not None:
        scan_context.finalize_ingestion(records, identifier=identifier, dry_run=args.dry_run)

    logging.info("Workspace ready at %s", paths.root)


def _run_handler_flow(args: argparse.Namespace) -> None:
    registry = HandlerRegistry(args.repo_root)
    if args.handler_command == "add":
        registry.add_handler(args.name, args.description)
    elif args.handler_command == "list":
        handlers = registry.list_handlers()
        if not handlers:
            print("No handlers registered yet.")
        else:
            for meta in handlers:
                print(f"{meta.name}: {meta.description} [{meta.status}] -> {meta.doc_path}")
    else:
        raise RepoMergerError(f"Unknown handler command: {args.handler_command}")


def _normalize_fragment_paths(paths: Sequence[Path]) -> List[Path]:
    normalized: List[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = Path(path).expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(resolved)
    return normalized


def _prepare_scan_context(
    args: argparse.Namespace,
    paths: WorkspacePaths,
    golden_path: Path,
) -> ScanContext:
    if not args.scan_source:
        raise RepoMergerError("--scan-source is required when --scan is enabled")
    scan_source = args.scan_source.expanduser().resolve()
    if not scan_source.exists():
        if args.scan_create_structure:
            logging.info("Creating scan source directory at %s", scan_source)
            scan_source.mkdir(parents=True, exist_ok=True)
        else:
            raise RepoMergerError(
                f"Scan source directory does not exist: {scan_source}. "
                "Use --scan-create-structure to create it."
            )

    candidates = scan_for_repos(
        scan_source,
        golden_pattern=args.scan_golden_pattern,
        fragment_pattern=args.scan_fragment_pattern,
        exclude=[paths.root],
    )
    manifest = ScanManifest(paths.root / "scan_manifest.json")
    context = ScanContext(
        manifest=manifest,
        report_path=paths.root / "scan_report.json",
    )

    if not candidates:
        logging.info("Scan found no repositories inside %s", scan_source)
        return context

    golden_resolved = golden_path.expanduser().resolve()
    for candidate in candidates:
        action = "ignored"
        reason = candidate.reason

        if candidate.classification == "fragment":
            entry = manifest.lookup(candidate.path)
            if entry and entry.get("digest") == candidate.digest:
                action = "existing"
                reason = "Fragment already ingested into workspace."
            else:
                context.add_pending_fragment(candidate)
                action = "ingest"
        elif candidate.classification == "golden":
            if candidate.path.expanduser().resolve() == golden_resolved:
                action = "workspace-golden"
                reason = "Matches provided golden repository."
            else:
                action = "report"
                reason = "Golden candidate detected; copy manually if desired."
        else:
            action = "unknown"

        context.add_report_entry(
            ScanReportEntry(
                source=str(candidate.path),
                classification=candidate.classification,
                confidence=candidate.confidence,
                action=action,
                reason=reason,
            )
        )

    logging.info(
        "Scan identified %d fragment candidate(s) awaiting ingestion.",
        len(context.pending_fragments),
    )
    return context


def _emit_report(
    workspace_paths: WorkspacePaths,
    analyses: Sequence[FragmentAnalysis],
    merges: Sequence[MergeResult] | None,
) -> None:
    if not analyses:
        logging.info("No analyses available; skipping report generation.")
        return
    summary = summarize_cli(analyses, merges)
    logging.info("\n%s", summary)
    report_path = workspace_paths.root / "report.md"
    write_markdown_report(report_path, analyses, merges)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except RepoMergerError as exc:
        logging.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        logging.error("Interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
