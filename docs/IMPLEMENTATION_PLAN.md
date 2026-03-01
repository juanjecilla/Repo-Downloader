# Implementation Plan

This document is the canonical execution plan for the next product cycle.
The implementation order is mandatory:

1. Complete documentation updates.
2. Implement packaging and release automation.
3. Implement provider auth profiles and CLI command surface.
4. Implement Codecov + Sentry observability changes.
5. Validate with tests and CI gates.

## Scope

In scope:
- Public PyPI release workflow for `repo-downloader`.
- Single-source packaging metadata in `pyproject.toml`.
- New auth command flow: `repo-downloader auth <provider>`.
- Secure credential storage using OS keyring + local profile metadata.
- Token resolution precedence for backup commands.
- Codecov integration with patch gate.
- Sentry opt-in integration for CLI error capture.
- Documentation and test coverage for all above.

Out of scope:
- OAuth/device-code flows.
- Enterprise/self-managed provider hosts in this phase.
- Breaking CLI redesign.

## Milestones

## M0: Documentation Complete (blocking)
Deliverables:
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/RELEASING.md`
- `docs/AUTH_PROFILES.md`
- `docs/OBSERVABILITY.md`
- Updated `docs/USAGE.md`
- Updated `docs/OPERATIONS.md`
- Updated `docs/FEATURE_CATALOG.md`
- Updated `docs/FUTURE_STEPS.md`
- Updated `docs/INDEX.md`

Exit criteria:
- Docs are internally consistent and linked from `docs/INDEX.md`.
- Docs describe all new CLI/public interface changes before code edits.

## M1: Packaging + Release Automation
Deliverables:
- `pyproject.toml` as the only packaging metadata source.
- `setup.py` removed.
- Package includes runtime modules: `downloader`, `data`, `utils`.
- SemVer tag-based version derivation.
- GitHub workflows:
  - `.github/workflows/release-tag.yml`
  - `.github/workflows/publish-testpypi.yml`
  - `.github/workflows/publish-pypi.yml`
- CI packaging checks integrated in `.github/workflows/pylint.yml`.

Exit criteria:
- Built wheel/sdist installs and runs CLI commands.
- Tagged release can publish to TestPyPI and PyPI using OIDC.

## M2: Auth Profiles + New CLI Command
Deliverables:
- `utils/auth_store.py` with keyring-backed secret storage.
- `downloader.py` supports `auth` command and auth profile options.
- Auth precedence in backup flow:
  1. `--token-env`
  2. keyring profile (`--auth-profile`)
  3. prompt fallback
- Tests for auth flows and regressions.

Exit criteria:
- `repo-downloader auth bitbucket|github|gitlab` works for setup/status/logout.
- Existing commands remain backward compatible.

## M3: Codecov + Sentry
Deliverables:
- `.coveragerc`
- `.codecov.yml`
- Coverage upload + patch gating in CI.
- `utils/sentry_utils.py` and CLI integration.
- Sentry env contract:
  - `REPO_DOWNLOADER_SENTRY_DSN`
  - `REPO_DOWNLOADER_SENTRY_ENVIRONMENT`
  - `REPO_DOWNLOADER_SENTRY_RELEASE`

Exit criteria:
- Patch coverage gate enforces >= 90%.
- Sentry is disabled by default and enabled only with DSN.

## Dependencies

Technical dependencies:
- Python packaging toolchain: `setuptools`, `wheel`, `build`, `twine`, `setuptools-scm`.
- Auth dependencies: `keyring`, `platformdirs`.
- Observability dependency: `sentry-sdk`.

Platform dependencies:
- Functional system keyring backend in runtime environment.
- GitHub repository configured for PyPI trusted publishing.

Repository dependencies:
- Provider implementations remain in `data/source/remote_sources.py`.
- Existing logging/redaction helpers remain in `utils/log_utils.py` and `utils/errors.py`.

## Risk Register

1. Keyring backend unavailable in CI/headless hosts.
- Impact: auth profile commands fail or become unreliable.
- Mitigation: clear fallback/error guidance and tests with mocked keyring backend.

2. Packaging version drift.
- Impact: release artifacts with incorrect versions.
- Mitigation: single-source metadata in `pyproject.toml` + tag-based version derivation.

3. Publish misconfiguration.
- Impact: failed or unintended package publication.
- Mitigation: separate TestPyPI and PyPI workflows + environment protections + OIDC only.

4. Secret leakage in logs/errors.
- Impact: credential exposure.
- Mitigation: enforce redaction in logger and error sanitization, add tests.

5. Coverage gate instability.
- Impact: noisy CI failures.
- Mitigation: patch-only hard gate and project soft target.

## Rollout Sequence

1. Merge docs changes.
2. Merge packaging/release workflow changes.
3. Validate release dry run with TestPyPI.
4. Merge auth command + keyring implementation.
5. Merge Codecov + Sentry changes.
6. Cut first stable SemVer tag from `main`.

## Acceptance Gates

Gate A: Docs gate
- All docs listed in M0 exist and are linked from `docs/INDEX.md`.

Gate B: Packaging gate
- `python -m build` succeeds.
- `twine check dist/*` succeeds.
- Wheel install smoke test passes.

Gate C: Auth gate
- Auth setup/status/logout tests pass for all providers.
- Backup command token precedence works.

Gate D: Observability gate
- Coverage XML generated and uploaded.
- Patch coverage gate active at >= 90%.
- Sentry opt-in behavior validated and redaction tests pass.

Gate E: Regression gate
- Existing command and provider contract tests remain green.
