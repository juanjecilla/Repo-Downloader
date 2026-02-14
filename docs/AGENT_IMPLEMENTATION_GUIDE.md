# Agent Implementation Guide

This file maps feature work to repository files so future agents can implement quickly.

## Where To Change What

### CLI and orchestration behavior
- `downloader.py`
- Use for: new flags, execution modes, summary output, retries, filtering, lock handling, resume behavior.

### Provider API behavior
- `data/source/provider_interface.py`
- `data/source/remote_sources.py`
- Use for: provider implementations (Bitbucket/GitHub/GitLab), auth flows, pagination, repo/branch API reads.

### Git sync primitives
- `data/source/git_source.py`
- Use for: clone/fetch/mirror update, checkout logic, git-level retries and errors.

### Shared utility logic
- `utils/repo_utils.py`
- `utils/url_utils.py`
- `utils/errors.py`
- Use for: repo parsing/filtering/pathing, clone URL selection, typed errors/redaction helpers.

### User and operations docs
- `README.md`
- `docs/USAGE.md`
- `docs/OPERATIONS.md`
- Use for: public behavior updates, runbook updates, examples and flags.

### Future planning docs
- `docs/FUTURE_STEPS.md`
- `docs/FEATURE_CATALOG.md`
- Use for: sequencing, priorities, feature details, status changes.

### Tests
- `tests/test_downloader.py`
- `tests/test_repo_utils.py`
- `tests/test_remote_sources.py`
- `tests/test_provider_contract.py`
- `tests/integration/test_git_source_integration.py`
- Use for: acceptance checks matching each feature.

## Standard Workflow For A Feature
1. Select feature ID from `docs/FEATURE_CATALOG.md`.
2. Implement only required code paths.
3. Add/adjust tests first for expected behavior.
4. Update usage/operations documentation.
5. Update feature status in `docs/FEATURE_CATALOG.md`.
