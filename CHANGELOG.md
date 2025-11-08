# Changelog

All notable changes to this project will be documented in this file and follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
