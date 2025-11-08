# Changelog

All notable changes to this project will be documented in this file and follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Packaged entry point (`pyproject.toml`, `python -m repo_merger`).
- Recursive `--scan` workflow that detects both bare and non-bare golden repos,
  generates `scan_report.json`/`scan_manifest.json`, and ingests only new
  fragments into workspaces.
- Bare repository detection during scanning and mirroring (bare goldens are
  cloned into working trees automatically).
- `--golden-pull` option that clones all `gh` user repositories into the
  workspace, comparing them against existing goldens and replacing only when the
  GitHub copy is newer.

### Changed
- Workspace preparation reuses existing directories unless `--force` is passed,
  keeping scans idempotent across runs.

## [0.1.0] - 2025-11-07

### Added
- Initial MVP tooling: CLI workspace bootstrap, fragment ingestion, inspection,
  reporting, merge/recovery scaffolding, handler registry automation.
- Documentation (README, PLAN, RUNBOOK, HANDLERS) covering workflows, CI badge,
  and developer guidance.
- GitHub Actions CI running `python -m pytest` on Python 3.12.
- Virtual environment helper script (`scripts/setup_venv.sh`) and
  `requirements.txt`.

### Notes
- Future versions will increment MAJOR.MINOR.PATCH per semver rules. Use tags
  like `v0.1.0`, `v0.2.0`, etc., when releasing.
