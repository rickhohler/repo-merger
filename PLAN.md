# Repository Merger Tool – Working Plan

## 1. Purpose and Scope
- Build a Python-based command-line helper that inspects multiple Git repositories and consolidates them under a single workspace structure.
- Treat one repository as the **golden** source (complete history, authoritative state) and the rest as **fragments** (partial clones, working copies, or loose files).
- Provide scaffolding for future automation (e.g., recovery, reconciliation, reporting) while failing loudly with actionable TODO hooks when encountering unhandled situations.

## 2. Terminology and Directory Layout
```
<workspace>/
  <repo-identifier>/
    golden/           # pristine clone of the canonical repo
    fragments/
      <fragment-id>/  # partial clones, extracted dirs, or raw files
```
- `repo-identifier`: derived from `.git/config` `remote "origin"` URL (fallbacks: directory name, explicit CLI flag, etc.).
- `fragment-id`: flexible naming to avoid collisions; may include hashing or timestamps later.
- Additional metadata (JSON/YAML) can sit alongside `golden/` to describe reconciliation sessions.

## 3. Script Entry Point
- `repo_merger.py` (later packageable). CLI managed via `argparse`:
  - `--workspace /path`
  - `--golden /path/to/repo`
  - `--fragment /path/to/repo_or_dir` (repeatable)
  - `--mode [analyze|merge|recover]` (start with `analyze`)
  - `--identifier explicit_name` (optional override)
  - `--dry-run`, `--verbose`

## 4. High-Level Workflow (Analyze Mode v1)
1. **Identify target repo**
   - Read `.git/config` from `--golden`.
   - Extract canonical name (repo slug) and default branch.
   - Create `<workspace>/<identifier>/` scaffold; refuse to overwrite unless `--force`.
2. **Materialize structure**
   - Copy/rsync (or `git clone --mirror`) golden repo into `golden/`.
   - Copy each fragment into `fragments/<generated-id>/` preserving original state.
3. **Inspection phase**
   - For git-backed fragments: capture `git status`, current branch, commit hash map.
   - For non-git fragments: generate file manifest + hashes to compare with golden.
   - Store inspection results in `analysis.json`.
4. **Comparison helpers**
   - Use `git diff --no-index` or Python `difflib` to compare file trees.
   - Determine fragment status categories: `in-sync`, `ahead`, `diverged`, `orphaned`, `non-git`.
5. **Reporting**
   - Emit CLI summary table and persist detailed report (JSON + human-readable markdown).
6. **Failure/TODO hooks**
   - For each unhandled situation, raise `NotImplementedError` with actionable message.
   - Auto-stub handler methods (see §7).

## 5. Future Modes
- **merge**: orchestrate applying fragment commits/changes onto golden (possibly using git worktrees or patches).
- **recover**: handle fragments missing `.git/` by reconstructing commits from timestamps/hashes.
- **auto-classify**: identify duplicate fragments, detect renamed directories, etc.
- **interactive**: prompt user when conflicts detected (later).

### 5.1 Merge Mode (Issue #7)
1. Extend CLI `--mode` choices to include `merge`.
2. When `merge` is selected:
   - Spawn a temporary worktree rooted at `<workspace>/<identifier>/worktrees/<fragment-id>/`.
   - For git fragments: fetch commits (if remote) or treat fragment as working tree and compute `git diff golden...fragment`. Apply via `git am` or `git apply`, recording conflicts.
   - For non-git fragments: rely on recovered repos (see §5.2) or use `git diff --no-index`.
3. Emit per-fragment merge results into `merge_report.json` with statuses `merged`, `conflicted`, `skipped`.
4. Expose `--resume-from <fragment-id>` to continue after resolving conflicts manually in the worktree.

### 5.2 Fragment Recovery (Issue #8)
1. Detect fragments lacking `.git/` or with unusable metadata during ingestion/inspection.
2. Introduce recovery pipeline:
   - Produce `manifests/<fragment-id>.json` capturing file paths, sizes, hashes, mtimes.
   - Infer commit groupings by modification windows (configurable threshold, e.g., 30 minutes).
   - Create synthetic git repo under `recovered/<fragment-id>/` seeded with golden base or empty tree.
   - Sequentially commit grouped files with synthetic author info and timestamps.
3. Update manifest to link recovered repo path so merge mode can treat it like standard git fragment.
4. Provide CLI flags: `--recovery-threshold`, `--recovery-base`.

### 5.3 Handler Registry Automation (Issue #9)
1. Create `repo_merger/handlers.py` module with registry structure storing handler metadata (name, status, description, doc path).
2. Add CLI subcommand `repo_merger handlers add <name> --description ...` to scaffold:
   - Code stub in `handlers.py`.
   - Placeholder test file.
   - Entry in `HANDLERS.md`.
3. Enhance analysis/reporting to:
   - Reference handler IDs when unhandled scenarios are logged.
   - Summarize missing handlers in `report.md`.
4. Add verification test ensuring doc + code entries stay consistent (e.g., parse `HANDLERS.md`).

## 6. Key Components
| Module | Responsibility |
| ------ | -------------- |
| `workspace.py` | Path handling, identifier derivation, collision avoidance, filesystem ops. |
| `inspector.py` | Logic to inspect repos/fragments and normalize metadata. |
| `comparator.py` | Compare fragment state to golden, categorize results. |
| `reporter.py` | Persist JSON/Markdown summaries; print CLI tables. |
| `handlers.py` | Registry for special-case logic (e.g., missing `.git`, detached HEAD). |
| `cli.py` | Argument parsing, mode dispatch, error handling. |

## 7. Extensibility Strategy
- Central registry `UnhandledScenarioRegistry` keeps track of handler names and associated metadata.
- When script hits unknown condition:
  - Logs entry in `analysis.json` with `status="unhandled"` + context payload.
  - Raises descriptive exception referencing stub name.
  - Generates placeholder method in `handlers.py` (if not existing) with docstring describing requirements.
- Companion doc `HANDLERS.md` enumerates each scenario and implementation status (manually maintained or auto-appended).

## 8. Data Artifacts
- `analysis.json`: fragment-by-fragment breakdown (paths, git metadata, status, TODO hooks).
- `report.md`: human-readable summary for operators.
- Optional: `manifests/<fragment-id>.json` for detailed file diff caches.

## 9. Error Handling & Logging
- Use Python `logging` with levels: INFO (progress), WARNING (recoverable oddities), ERROR (fatal/unhandled).
- Fail fast when workspace already populated unless explicit override.
- Validate prerequisites (git installed, readable directories) before mutating filesystem.

## 10. MVP Task List
1. Bootstrap CLI + workspace scaffolding (sections 3–4 step 1).
2. Implement fragment ingestion (copying + metadata capture).
3. Build inspection + categorization for:
   - Complete git repos (simple status checks).
   - Non-git directories (manifest generation).
4. Create reporting pipeline (JSON + Markdown).
5. Add handler registry + stub generation wiring.
6. Document runbooks (`README`, `HANDLERS.md`).

## 11. Open Questions
- How large can fragments be (affects copying strategy and hashing cost)?
- Should we deduplicate fragments sharing same commit hash automatically?
- How to prioritize merge direction when fragment diverges significantly?
- Desired storage format for recovered files with missing metadata?

## 12. Next Validation Steps
- Confirm sample golden/fragment repos to test assumptions.
- Decide on storage requirements (local disk vs. remote artifact store).
- Align on naming conventions for identifiers and fragment IDs.
- Define success criteria for `analyze` mode before implementing merge automation.
