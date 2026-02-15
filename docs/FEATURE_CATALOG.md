# Feature Catalog

This catalog is implementation-ready and meant for future agents.

Status values:
- `done`: implemented in current codebase.
- `next`: high-priority backlog.
- `planned`: medium-priority backlog.
- `later`: lower-priority or scale items.

## Core Platform Features

### F001 Structured Logging and Run Metadata
- Priority: `next`
- Status: `done`
- Goal: emit optional JSON lines logs with run ID, provider, repo, mode, action, duration, and outcome.
- Files:
  - `downloader.py`
  - `utils/errors.py`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - `--log-format json|text` and `--log-file <path>` options are available.
  - Every repo action emits a structured record.
  - Sensitive values (tokens, SSH paths if requested) are redacted.
- Tests:
  - Validate JSON parseability and required fields.
  - Validate no token leaks in output.

### F002 Include/Exclude Repository Filtering
- Priority: `next`
- Status: `done`
- Goal: allow repo selection with `--include` and `--exclude` patterns.
- Files:
  - `downloader.py`
  - `utils/repo_utils.py`
  - `docs/USAGE.md`
  - `tests/test_repo_utils.py`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Supports glob patterns by repo full name (`workspace/repo`).
  - Include applies first, exclude applies second.
  - Dry-run clearly displays skipped by filter reason.
- Tests:
  - Pattern match and precedence tests.

### F003 Branch Selection Controls
- Priority: `next`
- Status: `done`
- Goal: reduce checkout work in working mode.
- Files:
  - `downloader.py`
  - `data/source/git_source.py`
  - `docs/USAGE.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds `--branch`, `--branch-pattern`, and `--default-branch-only` options.
  - Branch selection applies only to working mode.
- Tests:
  - CLI parsing and selected branch subset behavior.

### F004 Repository-Level Retry and Error Classification
- Priority: `next`
- Status: `done`
- Goal: classify failures (`api`, `auth`, `clone`, `fetch`, `checkout`) and support scoped retries.
- Files:
  - `downloader.py`
  - `utils/errors.py`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds `--repo-retries` option.
  - Summary includes counts by failure type.
- Tests:
  - Simulated failure flows verify retry count and classification.

### F005 Run Locking
- Priority: `next`
- Status: `done`
- Goal: prevent concurrent runs against the same output root.
- Files:
  - `downloader.py`
  - `utils/repo_utils.py`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Lock file created at run start and removed at run end.
  - Second process exits with clear message unless `--force-lock` set.
- Tests:
  - Lock acquire/release behavior, stale lock handling.

## Provider Features

### F006 GitHub Provider Implementation
- Priority: `planned`
- Status: `done`
- Goal: implement real GitHub API support with token auth.
- Files:
  - `data/source/remote_sources.py`
  - `data/source/provider_interface.py`
  - `docs/USAGE.md`
  - `tests/test_remote_sources.py`
- Acceptance criteria:
  - Lists repositories with pagination.
  - Fetches repo details and branches.
  - Respects workspace/org filter semantics.
- Tests:
  - Auth error, pagination, and branch list mocks.

### F007 GitLab Provider Implementation
- Priority: `planned`
- Status: `done`
- Goal: implement real GitLab API support with personal/project tokens.
- Files:
  - `data/source/remote_sources.py`
  - `data/source/provider_interface.py`
  - `docs/USAGE.md`
  - `tests/test_remote_sources.py`
- Acceptance criteria:
  - Project listing and branch listing implemented.
  - Namespace/group filter behavior documented.
- Tests:
  - API mock tests for pagination and permission errors.

### F008 Provider Contract Regression Suite
- Priority: `planned`
- Status: `done`
- Goal: verify every provider satisfies the same contract and behavior.
- Files:
  - `tests/test_provider_contract.py`
  - `tests/test_remote_sources.py`
  - `tests/integration/`
- Acceptance criteria:
  - Shared provider fixture validates all contract methods.
  - Negative tests for auth/API failures are consistent.

### F009 Provider Behavior Parity Matrix
- Priority: `planned`
- Status: `done`
- Goal: ensure all providers behave the same for filtering, archive handling, and output paths.
- Files:
  - `docs/USAGE.md`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Documented matrix comparing provider option support.
  - Tests enforce expected parity where possible.

## Backup and Recovery Features

### F010 Snapshot Export from Mirrors
- Priority: `planned`
- Status: `done`
- Goal: export backup snapshots as `zip` or `tar.gz`.
- Files:
  - `downloader.py`
  - `utils/repo_utils.py`
  - `docs/USAGE.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds `--snapshot-format zip|tar.gz` and `--snapshot-dir`.
  - Snapshot naming includes timestamp and provider/workspace/repo.

### F011 Retention Policies
- Priority: `planned`
- Status: `done`
- Goal: automatic cleanup of old snapshots/working copies by age/count.
- Files:
  - `downloader.py`
  - `utils/repo_utils.py`
  - `docs/OPERATIONS.md`
  - `tests/test_repo_utils.py`
- Acceptance criteria:
  - Supports `--retain-days` and `--retain-count`.
  - Dry-run reports planned deletions.

### F012 Restore Helper Commands
- Priority: `planned`
- Status: `done`
- Goal: provide CLI helpers for restore verification.
- Files:
  - `downloader.py`
  - `docs/USAGE.md`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds subcommands for `validate-restore` and `list-backups`.
  - Validation checks refs and clone success.

### F013 Resumable Runs
- Priority: `planned`
- Status: `done`
- Goal: persist run checkpoints and resume after interruption.
- Files:
  - `downloader.py`
  - `utils/repo_utils.py`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds checkpoint file in output root.
  - `--resume` skips completed repos and continues.

## UX and Distribution Features

### F014 Config Profile Support
- Priority: `planned`
- Status: `planned`
- Goal: support config file driven runs (TOML/YAML).
- Files:
  - `downloader.py`
  - `docs/USAGE.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds `--config <path>`.
  - CLI args override config values.

### F015 Schedule Profiles and Automation Examples
- Priority: `planned`
- Status: `planned`
- Goal: document and template cron/automation usage.
- Files:
  - `docs/OPERATIONS.md`
  - `docs/FUTURE_STEPS.md`
- Acceptance criteria:
  - Include production-ready cron examples.
  - Include failure notification recommendations.

### F016 pipx / PyInstaller Packaging
- Priority: `planned`
- Status: `planned`
- Goal: ship easy installation targets.
- Files:
  - `README.md`
  - `docs/USAGE.md`
  - packaging config files (to be added)
  - `.github/workflows/pylint.yml`
- Acceptance criteria:
  - Documented install and run instructions for at least one packaged mode.

### F017 Containerized Runtime
- Priority: `later`
- Status: `later`
- Goal: provide Docker image for isolated execution.
- Files:
  - `Dockerfile` (new)
  - `docs/USAGE.md`
  - CI workflow files
- Acceptance criteria:
  - Image can execute full backup flow with mounted SSH key and output volume.

## Scale and Security Features

### F018 Concurrent Repository Sync
- Priority: `later`
- Status: `later`
- Goal: process repositories with a bounded worker pool.
- Files:
  - `downloader.py`
  - `data/source/git_source.py`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Adds `--workers` option.
  - Logs remain deterministic and grouped by repo.

### F019 Metrics and Health Report
- Priority: `later`
- Status: `later`
- Goal: emit run metrics and machine-readable health summary.
- Files:
  - `downloader.py`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - End-of-run summary export to JSON.
  - Includes per-mode duration and failure counters.

### F020 Secret Redaction and Input Hardening
- Priority: `next`
- Status: `next`
- Goal: ensure tokens/credentials are never logged or persisted insecurely.
- Files:
  - `downloader.py`
  - `utils/errors.py`
  - `docs/OPERATIONS.md`
  - `tests/test_downloader.py`
- Acceptance criteria:
  - Log redaction is centralized and enforced.
  - Validation errors never echo token content.

### F021 Compatibility and Regression Matrix
- Priority: `later`
- Status: `later`
- Goal: define and test supported OS/Python/Git combinations.
- Files:
  - `.github/workflows/pylint.yml`
  - `README.md`
  - `docs/USAGE.md`
  - test suite files
- Acceptance criteria:
  - Published compatibility matrix.
  - CI executes representative matrix coverage.

### F022 Code Review Automation on Protected Branches
- Priority: `next`
- Status: `done`
- Goal: ensure CodeRabbit auto review runs for pull requests targeting `main` and `develop`.
- Files:
  - `.coderabbit.yaml`
  - `docs/OPERATIONS.md`
- Acceptance criteria:
  - `.coderabbit.yaml` enables auto review.
  - Base branches include `main` and `develop`.
  - Draft pull requests are included in auto review scope.

## Already Implemented Features (Reference)

### B001 CLI Modes and Provider Selection
- Priority: `baseline`
- Status: `done`
- Delivered:
  - `--provider`, `--mode`, `--workspace`, `--output-dir`, `--include-archived`, `--dry-run`, `--ssh-key-path`, `--role`, `--token-env`.
- Files:
  - `downloader.py`
  - `docs/USAGE.md`

### B002 Bitbucket Stability Hardening
- Priority: `baseline`
- Status: `done`
- Delivered:
  - Session-based API access, retry policy, timeout handling, auth status/error mapping.
- Files:
  - `data/source/remote_sources.py`

### B003 Provider Contract and Stubs
- Priority: `baseline`
- Status: `done`
- Delivered:
  - Provider interface contract and GitHub/GitLab stubs.
- Files:
  - `data/source/provider_interface.py`
  - `data/source/remote_sources.py`

### B004 Backup Path and Sync Reliability
- Priority: `baseline`
- Status: `done`
- Delivered:
  - Deterministic output paths.
  - Mirror update and working fetch flows.
  - Typed sync exceptions.
- Files:
  - `data/source/git_source.py`
  - `utils/repo_utils.py`
  - `utils/errors.py`

### B005 Documentation and Test Foundation
- Priority: `baseline`
- Status: `done`
- Delivered:
  - Usage and operations docs.
  - Unit/integration test scaffolding.
  - CI runs tests and lint.
- Files:
  - `docs/USAGE.md`
  - `docs/OPERATIONS.md`
  - `tests/`
  - `.github/workflows/pylint.yml`
