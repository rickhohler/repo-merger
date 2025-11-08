from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from .auto import (
    ScanCandidate,
    ScanContext,
    ScanManifest,
    ScanReportEntry,
    scan_for_repos,
)
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
        help="Path to the authoritative (golden) repository to mirror (optional if --scan is used).",
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


@dataclass
class ScanRunConfig:
    golden: Path
    identifier: str
    context: ScanContext


def _run_workspace_flow(args: argparse.Namespace) -> None:
    scenario_registry = UnhandledScenarioRegistry(Path(__file__).resolve().parents[1])
    workspace_root = args.workspace.expanduser().resolve()

    if args.scan:
        scan_runs = _build_scan_runs(args, workspace_root)
        if not scan_runs:
            raise RepoMergerError("Scan did not identify any golden repositories.")
        for run in scan_runs:
            _process_single_run(
                args=args,
                workspace_root=workspace_root,
                golden_path=run.golden,
                fragments=args.fragments or [],
                explicit_identifier=run.identifier,
                scenario_registry=scenario_registry,
                scan_context=run.context,
            )
        return

    if not args.golden:
        raise RepoMergerError("--golden is required (or use --scan to discover repos).")

    _process_single_run(
        args=args,
        workspace_root=workspace_root,
        golden_path=args.golden,
        fragments=args.fragments or [],
        explicit_identifier=args.identifier,
        scenario_registry=scenario_registry,
        scan_context=None,
    )


def _process_single_run(
    args: argparse.Namespace,
    workspace_root: Path,
    golden_path: Path,
    fragments: Sequence[Path],
    explicit_identifier: str | None,
    scenario_registry: UnhandledScenarioRegistry,
    scan_context: ScanContext | None,
) -> None:
    golden_path = golden_path.expanduser().resolve()
    logging.info("Golden repo: %s", golden_path)
    logging.info("Workspace root: %s", workspace_root)

    identifier = explicit_identifier or derive_identifier(golden_path, None)
    logging.info("Workspace identifier: %s", identifier)

    paths = prepare_workspace(
        workspace_root=workspace_root,
        identifier=identifier,
        dry_run=args.dry_run,
        force=args.force,
    )

    fragment_paths = _normalize_fragment_paths(fragments)
    if scan_context is not None:
        fragment_paths.extend(scan_context.fragments_to_ingest())
        fragment_paths = _normalize_fragment_paths(fragment_paths)

    mirror_golden_repo(
        golden_path,
        paths.golden,
        dry_run=args.dry_run,
        replace=args.force,
    )

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


def _build_scan_runs(args: argparse.Namespace, workspace_root: Path) -> List[ScanRunConfig]:
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
        exclude=[workspace_root],
    )

    fragment_candidates = [c for c in candidates if c.classification == "fragment"]
    golden_candidates = [c for c in candidates if c.classification == "golden"]
    runs: List[ScanRunConfig] = []

    if args.golden:
        identifier = derive_identifier(args.golden.expanduser().resolve(), args.identifier)
        context = _build_scan_context(
            workspace_root=workspace_root,
            identifier=identifier,
            golden_path=args.golden,
            golden_candidate=None,
            fragment_candidates=fragment_candidates,
            unassigned=[],
        )
        runs.append(ScanRunConfig(golden=args.golden, identifier=identifier, context=context))
        return runs

    if not golden_candidates:
        raise RepoMergerError(
            "Scan found no golden repositories. Consider specifying --golden or adjust patterns."
        )

    assignments, unassigned = _assign_fragments_to_goldens(golden_candidates, fragment_candidates)
    for golden_candidate in golden_candidates:
        fragments = assignments.get(golden_candidate.path, [])
        identifier = derive_identifier(golden_candidate.path, None)
        context = _build_scan_context(
            workspace_root=workspace_root,
            identifier=identifier,
            golden_path=golden_candidate.path,
            golden_candidate=golden_candidate,
            fragment_candidates=fragments,
            unassigned=[c for c in unassigned if c not in fragments],
        )
        runs.append(ScanRunConfig(golden=golden_candidate.path, identifier=identifier, context=context))

    return runs


def _build_scan_context(
    workspace_root: Path,
    identifier: str,
    golden_path: Path,
    golden_candidate: ScanCandidate | None,
    fragment_candidates: Sequence[ScanCandidate],
    unassigned: Sequence[ScanCandidate],
) -> ScanContext:
    root = workspace_root / identifier
    manifest = ScanManifest(root / "scan_manifest.json")
    context = ScanContext(
        manifest=manifest,
        report_path=root / "scan_report.json",
    )

    golden_resolved = golden_path.expanduser().resolve()
    if golden_candidate:
        action = "candidate"
        reason = golden_candidate.reason
        if golden_candidate.path.expanduser().resolve() == golden_resolved:
            action = "workspace-golden"
            reason = "Matches discovered golden candidate."
        context.add_report_entry(
            ScanReportEntry(
                source=str(golden_candidate.path),
                classification="golden",
                confidence=golden_candidate.confidence,
                action=action,
                reason=reason,
            )
        )
    else:
        context.add_report_entry(
            ScanReportEntry(
                source=str(golden_path),
                classification="golden",
                confidence=1.0,
                action="workspace-golden",
                reason="User-specified golden repository.",
            )
        )

    for candidate in fragment_candidates:
        entry = manifest.lookup(candidate.path)
        if entry and entry.get("digest") == candidate.digest:
            action = "existing"
            reason = "Fragment already ingested into workspace."
        else:
            context.add_pending_fragment(candidate)
            action = "ingest"
            reason = candidate.reason
        context.add_report_entry(
            ScanReportEntry(
                source=str(candidate.path),
                classification="fragment",
                confidence=candidate.confidence,
                action=action,
                reason=reason,
            )
        )

    for candidate in unassigned:
        context.add_report_entry(
            ScanReportEntry(
                source=str(candidate.path),
                classification="fragment",
                confidence=candidate.confidence,
                action="unassigned",
                reason="No matching golden candidate identified.",
            )
        )

    return context


def _assign_fragments_to_goldens(
    golden_candidates: Sequence[ScanCandidate],
    fragment_candidates: Sequence[ScanCandidate],
) -> tuple[dict[Path, List[ScanCandidate]], List[ScanCandidate]]:
    mapping: dict[Path, List[ScanCandidate]] = {candidate.path: [] for candidate in golden_candidates}
    unassigned: List[ScanCandidate] = []
    if not golden_candidates:
        return mapping, list(fragment_candidates)

    for fragment in fragment_candidates:
        best_candidate: ScanCandidate | None = None
        best_score = 0
        for golden in golden_candidates:
            score = _path_similarity_score(golden.path, fragment.path)
            if score > best_score:
                best_score = score
                best_candidate = golden
        if best_candidate and best_score > 0:
            mapping.setdefault(best_candidate.path, []).append(fragment)
        else:
            unassigned.append(fragment)
    return mapping, unassigned


def _path_similarity_score(a: Path, b: Path) -> int:
    try:
        common = os.path.commonpath([a.expanduser().resolve(), b.expanduser().resolve()])
    except ValueError:
        return 0
    return len(Path(common).parts)


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
