# Operations Runbook

## Goals
- Run repeatable repository backups.
- Detect and triage failures quickly.
- Validate backup restore readiness.
- Operate release/auth/observability workflows safely.

## Scheduling Guidance
- Critical repositories: at least daily.
- Large organizations: every 4-12 hours in `mirror` mode.
- Use `working` mode only when branch-level working copies are required.

### Cron Example (every 6 hours)
```bash
0 */6 * * * cd /path/to/repo-downloader && /usr/bin/python3 downloader.py backup --config ./profiles/mirror.toml >> /var/log/repo-downloader.log 2>&1
```

## Standard Command Profiles

Mirror baseline:
```bash
repo-downloader backup \
  --provider bitbucket \
  --username my-user \
  --auth-profile default \
  --mode mirror \
  --output-dir ./backups
```

Scoped backup:
```bash
repo-downloader backup \
  --provider bitbucket \
  --username my-user \
  --auth-profile default \
  --mode both \
  --include "acme/*" \
  --exclude "acme/private-*"
```

Dry-run rollout:
```bash
repo-downloader backup --provider github --auth-profile default --mode both --dry-run
```

Restore drill:
```bash
repo-downloader validate-restore \
  --backup-path ./backups/bitbucket/acme/api-service.git \
  --restore-dir /tmp/api-service-restore
```

## Auth Profile Operations

Setup:
```bash
repo-downloader auth github --profile default
repo-downloader auth bitbucket --profile work
```

Status:
```bash
repo-downloader auth github --profile default --status
```

Logout:
```bash
repo-downloader auth github --profile default --logout
```

## Auth Incident / Debug Flow

1. Token not found:
- Check `--token-env` variable exists.
- Check profile exists and contains keyring secret.
- Re-run `repo-downloader auth <provider> --profile <name>`.

2. Bitbucket auth failure:
- Validate stored/provided `--username`.
- Validate app password scopes.

3. Keyring backend errors:
- Verify host keyring service availability.
- Use environment token path as temporary fallback.

4. Repeated provider auth errors:
- Run `repo-downloader auth <provider> --status`.
- Rotate token and re-run setup.

## Release Operations Runbook

Release policy:
- Stable releases only from `main`.
- Tag format `vX.Y.Z`.

Workflow order:
1. Trigger `.github/workflows/release-tag.yml` from `main`.
2. Verify `.github/workflows/publish-testpypi.yml` success.
3. Verify `.github/workflows/publish-pypi.yml` success.

Pre-release checks:
1. CI green on `main`.
2. Docs updated.
3. Packaging build and smoke tests passing.

Post-release checks:
1. `pip install --upgrade repo-downloader` resolves expected version.
2. CLI smoke:
   - `repo-downloader --help`
   - `repo-downloader list-backups --output-dir ./backups`

Rollback strategy:
- Publish a new patch release with fix.
- Do not attempt to overwrite existing PyPI artifacts.

## Observability Operations

Structured logs:
- Use `--log-format json --log-file <path>` for machine parsing.

Summary export:
- Use `--summary-file` for run-level metrics payloads.

Codecov:
- Patch coverage gate is `>= 90%`.
- Project coverage is informational.

Sentry:
- Disabled by default.
- Enable via environment:
  - `REPO_DOWNLOADER_SENTRY_DSN`
  - `REPO_DOWNLOADER_SENTRY_ENVIRONMENT`
  - `REPO_DOWNLOADER_SENTRY_RELEASE`

## Observability Troubleshooting

Codecov failures:
1. Inspect uncovered patch lines.
2. Add targeted tests.
3. Re-run coverage job.

Missing Sentry events:
1. Confirm DSN is set.
2. Confirm command path initialized Sentry.
3. Confirm redaction hook is not dropping required event fields.

Unexpected Sentry noise:
1. Review capture points and severity mapping.
2. Improve exception grouping and context.
3. Keep performance tracing disabled unless explicitly needed.

## Failure Handling
1. Authentication failures:
- Verify token validity and scopes.
- Verify provider account access.

2. SSH clone failures:
- Verify SSH key file and permissions.
- Verify host key trust/known_hosts.

3. API failures:
- Retry after transient outages.
- Check provider status pages.

4. Repository-specific failures:
- Increase `--repo-retries` for transient errors.
- Validate repository still exists and permissions are intact.

## Operational Safety
- Use `--dry-run` before new production rollouts.
- Keep backup/snapshot roots on durable storage.
- Never run concurrent jobs against same provider/output root.
- Use `--force-lock` only when lock is stale or intentionally superseded.
- Preserve mirror backups as source-of-truth artifacts.
