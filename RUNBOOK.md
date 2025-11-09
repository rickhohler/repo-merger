# Repo Merger Runbook

This guide walks through the day-to-day workflow for operating the repo-merger
tooling.

## 1. Prepare the workspace

```bash
python -m repo_merger run \
  --workspace /var/tmp/repo-merger \
  --golden ~/src/golden-repo \
  --fragment ~/src/fragment-a \
  --fragment ~/src/fragment-b \
  --mode analyze \
  --recover-missing
```

> Tip: When using `--scan` you may omit `--golden`; the CLI will discover each
> golden repository under `--scan-source` and build the workspace structure
> automatically.

Key notes:
- The command mirrors the golden repo into `<workspace>/<identifier>/golden/`.
- Fragments are copied under `fragments/<fragment-id>/`.
- Non-git fragments are optionally recovered into synthetic repos when
  `--recover-missing` is used.

## 2. Review analysis output

- `analysis.json`: machine-readable summary of fragment status, git metadata,
  manifests, and handler references.
- `report.md`: human-readable summary (statuses, diffs, manifests, merge
  results). The CLI prints a concise version as well.
- `manifests/<fragment-id>.json`: file-level hashes for non-git fragments.

Check for `handlers` entries referencing stubs such as `handle_missing_fragment`.
These signal the tool encountered a situation that needs custom logic.

## 3. Handle unhandled scenarios

When a handler is referenced:
1. Locate the stub under `repo_merger/handlers/handle_<name>.py` and the matching
   test under `tests/handlers/test_handle_<name>.py`.
2. Implement the recovery/inspection logic and update the test to assert the new
   behavior.
3. Update `HANDLERS.md` to reflect the handler’s status and add any runbook
   notes needed for future operators.
4. Re-run the analyze/merge command to verify the handler is no longer reported.

You can also scaffold handlers manually:

```bash
python -m repo_merger handlers add missing-remote --description "Handle repos without origin URL"
python -m repo_merger handlers list
```

## 4. Merge changes (optional)

Once fragments are inspected, use merge mode to stage their changes against the
golden repo:

```bash
python -m repo_merger run \
  --workspace /var/tmp/repo-merger \
  --golden ~/src/golden-repo \
  --fragment ~/src/fragment-a \
  --mode merge \
  --resume-from 002-fragment-b
```

Each fragment gets a git worktree under `worktrees/<fragment-id>/`. Resolve any
conflicts directly in that worktree, then rerun merge mode with
`--resume-from <next-id>` to continue processing.

## 5. Tests and validation

Before committing changes to handlers or core tooling:

```bash
python -m pytest
```

Ensure new handlers include meaningful tests under `tests/handlers/` and that
documentation (README, HANDLERS.md, this runbook) stays in sync with the
current workflow.

## Appendix: Virtual environment setup

Use the helper script to create a local venv and install dependencies:

```bash
./scripts/setup_venv.sh .venv
source .venv/bin/activate
python -m pytest
```

Override the interpreter via `PYTHON_BIN=/path/to/python ./scripts/setup_venv.sh`
if required.

## Appendix: Releases

- Update `CHANGELOG.md` with entries under the next version heading.
- Bump the README version badge (if desired) and create a git tag, e.g.
  `git tag v0.1.0 && git push origin v0.1.0`.
- Keep release numbers aligned with Semantic Versioning.

## Appendix: Repo discovery helper

`python -m repo_merger run --scan` scans `--scan-source` (default `~/REPOS`) for
golden repos (`--scan-golden-pattern`, default `*golden*`) and fragments
(`--scan-fragment-pattern`, default `fragment*`). Example:

```bash
python -m repo_merger run \
  --workspace /var/tmp/repo-merger \
  --scan \
  --scan-source $HOME/REPOS \
  --scan-create-structure \
  --recover-missing \
  --dry-run
```

Operator checklist:
1. Populate `--scan-source` with the golden repo and fragment directories (or
   let `--scan-create-structure` create it).
2. Run the scan command with your desired flags (`--mode merge`, `--dry-run`,
   etc.). Each detected golden repo (bare or non-bare) is mirrored into its own
   workspace identifier and any new fragments are ingested automatically.
3. Inspect `scan_report.json` for classification decisions (including bare
   repo detections) and `scan_manifest.json` for ingestion history. Each report
   now stores its results under the `identifier` map keyed by the source label
   (`--scan-source-id` or the scan directory name), so rerunning the same
   identifier replaces that section while other identifiers stay available.
4. Read `scan_failed.txt` for absolute paths requiring follow-up; since
   `scan_report.json` already records every processed directory, `scan_succeeded`
   is no longer emitted.

## Appendix: Golden pull

Run `python -m repo_merger run --workspace <root> --golden-gh-pull` (after
`gh auth login`) to clone every repository you own into the workspace golden
structure. Existing goldens are compared to the freshly cloned copy; only newer
repos replace the workspace. Combine with `--scan` afterwards to ingest
fragments.
