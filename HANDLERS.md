# Handler Catalog

The handler registry tracks unhandled scenarios discovered while running the
repo-merger tool. When the analyzer or merger hits a situation it cannot
process, it logs the scenario, generates a stub under `repo_merger/handlers/`,
adds a placeholder test in `tests/handlers/`, and records an entry here plus in
`handlers_registry.json`.

## Workflow

1. Run the tool (e.g., `python -m repo_merger run ... --mode analyze`).
2. If an unhandled scenario appears in the CLI/report, open this file to locate
   the corresponding handler stub.
3. Implement the logic in `repo_merger/handlers/<handler>.py`, update or expand
   the auto-generated test, and mark the status below (e.g., `IN_PROGRESS`,
   `DONE`).
4. Re-run the tool to ensure the scenario is now handled. Remove or update the
   handler entry when no longer needed.

Existing handlers:

- *(auto-generated entries will be appended here as new scenarios are logged.)*
