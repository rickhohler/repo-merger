# Repo Merger

![CI](https://github.com/rickhohler/repo-merger/actions/workflows/ci.yml/badge.svg)
![Version](https://img.shields.io/badge/version-v0.1.0-blue)

Tooling that consolidates multiple repository directories into a single workspace
containing a **golden** copy (authoritative source) and **fragment** copies
(partials, stale clones, recovered files, etc.).

## Usage (MVP)

```bash
python -m repo_merger run \
  --workspace /tmp/merges \
  --golden /path/to/golden-repo \
  --fragment /path/to/fragment-a \
  --fragment /path/to/fragment-b \
  --mode analyze \
  --recover-missing \
  --dry-run
```

Key flags:

- `--workspace`: directory that will hold the merged workspace(s).
- `--golden`: local path to the complete repository you trust the most (optional when using `--scan`).
- `--fragment`: optional partial copies to mirror into the workspace (repeatable).
- `--identifier`: override the derived workspace identifier (defaults to origin slug).
- `--mode`: `analyze` (default) or `merge` for applying fragment changes via git worktrees.
- `--force`: allow overwriting an existing workspace directory.
- `--recover-missing`: recover fragments without `.git/` metadata into synthetic repos.
- `--resume-from`: resume `--mode merge` at a particular fragment ID.
- `--scan`, `--scan-source`, `--scan-golden-pattern`, `--scan-fragment-pattern`: auto-discover golden and fragment repos in arbitrary directories.
- `--dry-run`: log the planned filesystem actions without writing.
- `--verbose`: enable debug logging for troubleshooting.

Running without `--dry-run` mirrors the golden repository into
`<workspace>/<identifier>/golden/` and prepares an empty
`<workspace>/<identifier>/fragments/` directory for future steps.

Supplying one or more `--fragment` paths copies those directories or files into
`<workspace>/<identifier>/fragments/<fragment-id>/` (IDs are derived from the
original path plus a digest). Metadata for the latest ingestion run is written
to `<workspace>/<identifier>/fragments_manifest.json`. With `--recover-missing`,
fragments that lack `.git/` metadata are mirrored into
`<workspace>/<identifier>/recovered/<fragment-id>/` as synthetic git repos so the
merge workflow can treat them consistently.

Running with `--mode merge` creates git worktrees under
`<workspace>/<identifier>/worktrees/<fragment-id>/`, overlays the fragment
contents, and captures results in `merge_report.json`.

Analyze mode always produces `<workspace>/<identifier>/analysis.json` with
fragment statuses (`in-sync`, `diverged`, `non-git`, etc.). Non-git fragments
also write manifests to `manifests/<fragment-id>.json` containing file hashes to
aid manual reconciliation.

A consolidated Markdown summary is written to
`<workspace>/<identifier>/report.md` after each analyze or merge run, and the CLI
prints a concise text summary for quick review.

## Handler registry & unhandled scenarios

If the tooling encounters a situation it cannot process (e.g., a fragment
expected to be a git repo but `.git/` is missing), it automatically logs the
scenario, generates a handler stub under `repo_merger/handlers/`, and updates
`HANDLERS.md` plus `tests/handlers/`. You can also manage handlers manually:

```bash
python -m repo_merger handlers add missing-remote --description "Handle repos without origin URL"
python -m repo_merger handlers list
```

When a handler stub is added, edit the generated file and matching test to
implement the recovery logic, update `HANDLERS.md` with status notes, and rerun
`repo_merger run ...` to confirm the scenario is resolved. See `RUNBOOK.md` for a
full workflow, including how to interpret `analysis.json`, `report.md`, and
merge outputs.

### Handler registry CLI

Unhandled scenarios can register handler stubs via:

```bash
python -m repo_merger handlers add missing-remote --description "Handle repos without origin URL"
python -m repo_merger handlers list
```

This scaffolds `repo_merger/handlers/handle_missing_remote.py`, a matching test
stub under `tests/handlers/`, updates `HANDLERS.md`, and persists metadata in
`handlers_registry.json`.

Install dependencies (standard library only at the moment) and run tests with:

```bash
python -m pytest
```

## Local environment

```bash
./scripts/setup_venv.sh .venv
source .venv/bin/activate
pip install -e .            # optional, installs CLI entry point
repo-merger run --help      # or: python -m repo_merger run --help
```

The setup script creates a virtual environment (default `.venv`), upgrades pip,
and installs dependencies from `requirements.txt` (currently `pytest` for the
test suite). Use `PYTHON_BIN=/usr/bin/python3 ./scripts/setup_venv.sh` if you
need a specific interpreter path. Installing the project with `pip install -e .`
exposes the `repo-merger` console script via entry points.

### Scanning directories for golden/fragment repos

Use the `--scan` option to auto-detect repositories before running analyze or
merge modes. If you omit `--golden`, every golden repository discovered during
the scan is mirrored into its own workspace identifier automatically:

```bash
python -m repo_merger run \
  --workspace $HOME/REPOS/repo-merger-workspaces \
  --scan \
  --scan-source $HOME/REPOS \
  --scan-create-structure \
  --scan-golden-pattern "*golden*" \
  --scan-fragment-pattern "fragment*" \
  --dry-run
```

Workflow:
1. Point `--scan-source` (default `~/REPOS`) at a directory containing your
   repos. Enable `--scan-create-structure` to create it if missing.
2. Adjust `--scan-golden-pattern` / `--scan-fragment-pattern` as needed. If your
   directories are not named clearly, you can pass wildcards such as `"*"` and
   let the `.git` heuristics classify each repo (bare repositories are treated
   as goldens automatically).
3. Run the command above (append regular flags such as `--mode merge`,
   `--recover-missing`, etc.). The CLI will create or reuse workspaces for each
   detected golden repo and ingest any new fragments automatically. Bare
   repositories are cloned into working trees before analysis so they can be
   compared like non-bare repos.
4. Review `scan_report.json` and `scan_manifest.json` inside each workspace to
   see what was discovered, ingested, or skipped (including classifications of
   “likely golden” vs “fragment”). Re-running the scan is idempotent; previously
   ingested fragments are skipped unless their content changes.

### Bare repositories

Scans detect both non-bare and bare Git repositories. When a bare repository is
selected as a golden candidate, repo-merger clones it into the workspace to
produce a working tree before running analysis/merge. Bare fragments are logged
with lower confidence and require operator approval (e.g., via
`--recover-missing`) before ingestion.

### Preparing workspaces in bulk

Use `scripts/prepare_repo_workspaces.sh` to scan `REPOS_SOURCES`, create the
expected workspace layout inside `WORKSPACES_ROOT`, and run repo-merger for each
golden repo:

```bash
REPOS_SOURCES=$HOME/REPOS \
WORKSPACES_ROOT=$HOME/REPOS/repo-merger-workspaces \
./scripts/prepare_repo_workspaces.sh --dry-run
```

Additional flags/overrides (e.g., `--mode merge`, `GOLDEN_PATTERN=my-golden`) can
be provided just like the discovery script.

## Versioning & changelog

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See `CHANGELOG.md` for release notes. Tag releases as `vMAJOR.MINOR.PATCH`
(e.g., `v0.1.0`) once changes are merged to `main`.

> CI: All pushes/PRs run `python -m pytest` via GitHub Actions (`.github/workflows/ci.yml`) on Python 3.12.
