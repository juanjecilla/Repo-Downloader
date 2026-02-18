# Releasing

This runbook defines production release policy for `repo-downloader`.

## Policy

- Release channel: stable only from `main`.
- Versioning: SemVer (`MAJOR.MINOR.PATCH`).
- Tag format: `vX.Y.Z`.
- Version source: git tags, derived at build time.

## Release Inputs

- Branch: `main`.
- Bump type: `patch`, `minor`, or `major`.
- Clean CI state on `main`.

## Workflow Topology

1. `release-tag.yml`
- Manual workflow dispatch.
- Computes next SemVer tag from latest `v*` tag.
- Creates and pushes annotated tag.
- Creates GitHub Release.

2. `publish-testpypi.yml`
- Triggered by pushed tags `v*`.
- Builds wheel/sdist, runs `twine check`, publishes to TestPyPI.
- Runs install smoke test against TestPyPI.

3. `publish-pypi.yml`
- Triggered after successful TestPyPI workflow.
- Rebuilds artifacts from tagged commit.
- Publishes to PyPI using OIDC trusted publishing.

## OIDC Trusted Publishing

Required GitHub environment configuration:
- `testpypi` environment for TestPyPI publish job.
- `pypi` environment for PyPI publish job.
- Optional required reviewers/approvals for `pypi`.

No long-lived PyPI API token should be stored when OIDC is configured.

## Release Checklist

Pre-release:
1. Ensure `main` includes intended changes.
2. Ensure CI on `main` is green.
3. Review docs for release readiness.
4. Check workflows and environment protections are active.

Release:
1. Trigger `release-tag.yml` with desired bump.
2. Confirm tag and GitHub Release creation.
3. Confirm TestPyPI publish and smoke install succeed.
4. Confirm PyPI publish workflow succeeds.

Post-release:
1. Confirm `pip install repo-downloader` resolves new version.
2. Run CLI smoke check:
   - `repo-downloader --help`
   - `repo-downloader list-backups --output-dir ./backups`
3. Update release notes if needed.

## Rollback Procedure

If TestPyPI fails:
- Fix issue on `main`.
- Create a new patch tag.

If PyPI publish fails before publish step:
- Fix workflow/config.
- Re-run workflow for same tag.

If broken release already published to PyPI:
- Do not overwrite files.
- Publish a new patch release with fix (e.g., `vX.Y.(Z+1)`).
- Add clear release note marking the prior version as superseded.

## Versioning Rules

- `PATCH`: bug fixes, docs-only packaging adjustments, CI-only fixes.
- `MINOR`: new backward-compatible CLI options/commands and feature additions.
- `MAJOR`: breaking CLI or behavior changes.
