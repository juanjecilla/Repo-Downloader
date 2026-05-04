# Known Issues and Technical Debt

This document tracks known quality gaps, design limitations, and technical debt in the current codebase.
Issues are grouped by severity. Corresponding improvement features are referenced where applicable.

## High Priority

### KI-001 No static type checking
- **Symptom:** Type errors (wrong arg types, missing attributes) are only caught at runtime.
- **Root cause:** No `mypy` configuration exists; no type annotations on function signatures.
- **Impact:** Regressions in provider or utility code can reach production undetected.
- **Fix:** Add mypy and annotate core modules. See `F028`.

### KI-002 Codecov gate is non-blocking
- **Symptom:** Coverage can silently drop on any PR — Codecov posts a comment but does not block merge.
- **Root cause:** `.codecov.yml` has `informational: true` on both project and patch checks.
- **Impact:** Test quality regresses without any automated enforcement.
- **Fix:** Set `informational: false` and enforce a ≥ 80% threshold. See `F031`.

### KI-003 `downloader.py` violates Single Responsibility Principle
- **Symptom:** `downloader.py` is 2014 lines containing argument parsing, run orchestration, provider selection, worker management, snapshot logic, and retention — all in one file.
- **Root cause:** Organic growth; no refactoring phase was planned.
- **Impact:** Hard to test individual paths; coverage is artificially low; changes risk cross-cutting regressions.
- **Fix:** Decompose into `cli.py`, `orchestrator.py`, and `commands/` subpackage. See `F032`.

## Medium Priority

### KI-004 Pylint configuration is overly permissive
- **Symptom:** 25+ pylint rules are disabled in `.pylintrc` including complexity checks (`too-many-arguments`, `too-many-locals`), docstring checks, and style rules.
- **Root cause:** Rules were disabled incrementally to silence noise rather than fix root causes.
- **Impact:** Real code quality issues (over-complex functions, missing docs) go unreported.
- **Fix:** Re-enable rules one group at a time as code is refactored. Tracked alongside `F027`.

### KI-005 Integration tests require live network access
- **Symptom:** Tests in `tests/integration/` make real API or git calls; they fail or are skipped in environments without credentials/network.
- **Root cause:** No VCR cassette recording or test doubles for network calls in integration layer.
- **Impact:** CI on forks or air-gapped environments cannot fully validate integration paths.
- **Fix:** Add `responses` or `pytest-recording` fixtures to record and replay API interactions.

### KI-006 No pre-commit hooks
- **Symptom:** Lint, format, and type errors are only caught by CI — not locally before push.
- **Root cause:** No `.pre-commit-config.yaml` exists in the repo.
- **Impact:** Developers push code that fails CI, adding round-trip latency to feedback.
- **Fix:** Add pre-commit with ruff + mypy + bandit. See `F029`.

### KI-007 No security scanning in CI
- **Symptom:** Known CVEs in dependencies and common code security issues (hardcoded paths, shell injection patterns) are not automatically flagged.
- **Root cause:** No `bandit` or `pip-audit` step in any workflow.
- **Impact:** Security regressions can slip through PR review.
- **Fix:** Add a dedicated `security` CI job. See `F030`.

## Low Priority

### KI-008 No CHANGELOG
- **Symptom:** Release history is only visible via git tags and PR titles; no human-readable changelog exists.
- **Root cause:** No changelog automation was configured during release pipeline setup.
- **Impact:** Users cannot easily see what changed between versions.
- **Fix:** Add `git-cliff` or `commitizen` with conventional commits. See `F033`.

### KI-009 No dependency version pinning
- **Symptom:** `requirements.txt` specifies package names without version constraints (e.g., `GitPython` not `GitPython==3.1.43`).
- **Root cause:** Pinning was not part of initial setup.
- **Impact:** `pip install` on a fresh environment may resolve incompatible versions in the future.
- **Fix:** Pin exact versions in `requirements.txt`; use `pip-compile` from `pip-tools` to manage updates.

### KI-010 Sentry DSN not validated at startup
- **Symptom:** If Sentry is configured but the DSN is invalid or the network is unreachable, errors are silently dropped.
- **Root cause:** `utils/sentry_utils.py` catches all init exceptions to avoid breaking the tool.
- **Impact:** Operators may believe Sentry is active when it is not.
- **Fix:** Add a startup log event (`sentry.init_status`) indicating whether Sentry initialized successfully.
