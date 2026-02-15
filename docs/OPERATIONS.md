# Operations Runbook

## Goals
- Run repeatable repository backups.
- Detect and handle failures quickly.
- Validate backups are restorable.

## Recommended Schedule
- Critical repositories: at least daily.
- Large/active organizations: every 4-12 hours for mirror mode.
- Run `working` mode only when browsing or branch-level local validation is needed.

## Suggested Command Profiles
### Profile: Mirror baseline (recommended)
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode mirror \
  --output-dir ./backups
```

### Profile: Full backup for selected workspace
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --workspace acme \
  --mode both \
  --output-dir ./backups
```

### Profile: Scoped backup with include/exclude filters
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --include "acme/*" \
  --exclude "acme/private-*"
```

### Profile: Safe preview before rollout
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --dry-run
```

### Profile: Retry transient repository failures
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --repo-retries 2
```

### Profile: Force lock replacement (exception use)
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --force-lock
```

## Observability and Logs
- Default `text` logs include per-repository actions and summary counters.
- `json` log format emits structured events with `run_id`, timestamps, provider, repository, mode, action, outcome, and durations where applicable.
- Investigate any `[ERROR]` or `[WARN]` lines immediately.
- Write structured logs to a file for auditing:
  ```bash
  python3 downloader.py \
    --provider bitbucket \
    --username my-user \
    --token-env BITBUCKET_APP_PASSWORD \
    --mode both \
    --log-format json \
    --log-file ./logs/backup-run.jsonl
  ```
- Capture text output with shell redirection:
  ```bash
  python3 downloader.py ... > backup.log 2>&1
  ```
- End-of-run output includes failure-type counters for failed repositories (`api`, `auth`,
  `clone`, `fetch`, `checkout`, `other`) to help direct investigation.
- Lock acquire/release events are logged with lock path and replacement metadata.

## Failure Handling
1. Authentication errors:
   - Verify token/app-password and `--username`.
   - Confirm token scopes are sufficient.
2. SSH clone errors:
   - Verify SSH key exists and matches `--ssh-key-path`.
   - Validate host key/known_hosts setup.
3. API failures:
   - Retry after transient outage.
   - Review provider status pages.
4. Repository-specific failures:
   - Re-run command and inspect the repository block.
   - Increase `--repo-retries` for transient clone/fetch/api failures.
   - Confirm repository still exists and access is granted.

## Restore Validation
Run this periodically to verify backups:
1. Pick a mirror repo path, for example:
   - `./backups/bitbucket/acme/api-service.git`
2. Clone from local mirror:
   ```bash
   git clone ./backups/bitbucket/acme/api-service.git /tmp/api-service-restore-test
   ```
3. Inspect refs/history:
   ```bash
   git -C /tmp/api-service-restore-test branch -a
   git -C /tmp/api-service-restore-test log --oneline -n 10
   ```
4. Remove temporary restore clone after validation.

## Operational Safety
- Use `--dry-run` before first production run.
- Keep backup root on durable storage.
- Avoid deleting existing backup paths outside planned retention procedures.
- Preserve mirrors as source-of-truth backup artifacts.
- Never run two jobs against the same provider/output root concurrently.
- Use `--force-lock` only when an existing lock is stale or intentionally superseded.

## Pull Request Review Automation
- CodeRabbit automatic review is configured in `.coderabbit.yaml`.
- Any pull request targeting `main` or `develop` triggers auto review, including draft pull requests.

## Future Operational Enhancements
Future operational work items are tracked in:
- `docs/FUTURE_STEPS.md`
- `docs/FEATURE_CATALOG.md`
