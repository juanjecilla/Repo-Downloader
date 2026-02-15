# Future Steps

This document is the implementation sequence for future agents.  
Use it with `docs/FEATURE_CATALOG.md`.

## Current Baseline
- Bitbucket provider works with retries/timeouts.
- Backup modes `mirror`, `working`, `both` are implemented.
- Workspace filter, archive toggle, dry-run, and output layout are implemented.
- GitHub provider is implemented; GitLab provider remains a stub.

## Phase 1: Reliability and Operability (P1)
Goal: make production backup runs predictable and easy to debug.

1. Implement structured logging and run IDs (`F001`).
2. Implement include/exclude repository filtering (`F002`).
3. Implement branch selection controls for working mode (`F003`).
4. Add per-repository retry/error classification in the sync loop (`F004`).
5. Add lock file/concurrent run protection (`F005`).

Definition of done:
- Operators can run backups with machine-parseable logs.
- Runs are safe against overlapping execution.
- Scoped runs (repo filters + branch filters) are possible.

Progress:
- `F001` completed.
- `F002` completed.
- `F003` completed.
- `F004` completed.
- `F005` completed.

## Phase 2: Provider Expansion (P2)
Goal: support multi-provider backups without changing CLI semantics.

1. Implement GitHub provider (`F006`).
2. Implement GitLab provider (`F007`).
3. Add provider contract tests with mocked API pagination/auth errors (`F008`).
4. Add provider parity tests for output layout and filtering (`F009`).

Definition of done:
- `--provider github` and `--provider gitlab` perform real backups.
- All providers share equivalent behavior for mode/output/filter options.

Progress:
- `F006` completed.
- `F007` completed.
- `F008` completed.
- `F009` completed.

## Phase 3: Backup Product Features (P3)
Goal: improve recovery workflows and storage management.

1. Add snapshot export (zip/tar) from mirrors (`F010`).
2. Add retention policy for snapshots/working copies (`F011`).
3. Add restore helper commands and validation workflow (`F012`).
4. Add resumable runs with checkpoint state (`F013`).

Definition of done:
- Snapshot + retention + restore flows are documented and tested.
- Large runs can resume from checkpoint after interruption.

Progress:
- `F010` completed.
- `F011` completed.

## Phase 4: UX and Distribution (P4)
Goal: make tool easy to adopt across environments.

1. Add config profiles file support (`F014`).
2. Add schedule profile examples and automation guidance (`F015`).
3. Add packaging targets (pipx/PyInstaller) (`F016`).
4. Add Docker image and CI release pipeline (`F017`).

Definition of done:
- Users can run from config profiles.
- At least one packaged distribution path is production-ready.

## Phase 5: Scale and Governance (P5)
Goal: support larger organizations and safer operations.

1. Add concurrency controls for repo sync workers (`F018`).
2. Add metrics/health summary output and optional Prometheus text export (`F019`).
3. Add secret handling hardening and redaction (`F020`).
4. Add compatibility matrix + regression suite (`F021`).

Definition of done:
- High-volume org backup runs complete predictably.
- Security and compatibility checks are standardized.

## File Ownership Map For Future Work
- CLI orchestration: `downloader.py`
- Provider contract and implementations: `data/source/provider_interface.py`, `data/source/remote_sources.py`
- Git sync operations: `data/source/git_source.py`
- Common errors/helpers: `utils/errors.py`, `utils/repo_utils.py`, `utils/url_utils.py`
- User docs: `docs/USAGE.md`, `docs/OPERATIONS.md`
- Future planning backlog: `docs/FEATURE_CATALOG.md`, `docs/FUTURE_STEPS.md`
- Tests: `tests/` and `tests/integration/`

## Agent Workflow Recommendation
1. Pick one feature ID from `docs/FEATURE_CATALOG.md`.
2. Implement only the files listed under that feature.
3. Add/update tests named in that feature.
4. Update `docs/USAGE.md` and `docs/OPERATIONS.md` if behavior changes.
5. Mark status in the feature entry after merge.
