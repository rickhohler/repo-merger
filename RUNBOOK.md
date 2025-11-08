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
