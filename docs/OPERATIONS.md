# Operations Runbook

## Goals
- Run repeatable repository backups.
- Detect and handle failures quickly.
- Validate backups are restorable.

## Recommended Schedule
- Critical repositories: at least daily.
- Large/active organizations: every 4-12 hours for mirror mode.
- Run `working` mode only when browsing or branch-level local validation is needed.

## Scheduling Examples
### Cron: every 6 hours mirror backup
```bash
0 */6 * * * cd /path/to/repo-downloader && /usr/bin/python3 downloader.py backup --config ./profiles/mirror.toml >> /var/log/repo-downloader.log 2>&1
```

### Cron: daily full backup + restore validation
```bash
15 2 * * * cd /path/to/repo-downloader && /usr/bin/python3 downloader.py backup --config ./profiles/full.toml >> /var/log/repo-downloader.log 2>&1
45 2 * * * cd /path/to/repo-downloader && /usr/bin/python3 downloader.py validate-restore --backup-path ./backups/bitbucket/acme/api-service.git --restore-dir /tmp/api-service-restore >> /var/log/repo-downloader.log 2>&1
```

### systemd timer (Linux)
`/etc/systemd/system/repo-downloader.service`:
```ini
[Unit]
Description=Repo-Downloader Backup Run

[Service]
Type=oneshot
WorkingDirectory=/path/to/repo-downloader
ExecStart=/usr/bin/python3 /path/to/repo-downloader/downloader.py backup --config ./profiles/full.toml
```

`/etc/systemd/system/repo-downloader.timer`:
```ini
[Unit]
Description=Run Repo-Downloader every 6 hours

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

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

### Profile: GitHub organization backup
```bash
python3 downloader.py \
  --provider github \
  --token-env GITHUB_TOKEN \
  --workspace acme-org \
  --mode both \
  --output-dir ./backups
```

### Profile: GitLab group backup
```bash
python3 downloader.py \
  --provider gitlab \
  --token-env GITLAB_TOKEN \
  --workspace acme-group \
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

### Profile: Mirror snapshots for offline transfer
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode mirror \
  --snapshot-format tar.gz \
  --snapshot-dir ./snapshots
```

### Profile: Retention cleanup for snapshots/working copies
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --snapshot-format zip \
  --snapshot-dir ./snapshots \
  --retain-days 30 \
  --retain-count 20
```

### Profile: Inventory existing backups
```bash
python3 downloader.py list-backups --output-dir ./backups
```

### Profile: Validate restore drill
```bash
python3 downloader.py validate-restore \
  --backup-path ./backups/bitbucket/acme/api-service.git \
  --restore-dir /tmp/api-service-restore
```

### Profile: Resume interrupted backup run
```bash
python3 downloader.py backup \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --resume
```

### Profile: Config-driven run
```bash
python3 downloader.py backup --config ./profiles/daily.toml
```

### Profile: Parallel repository workers
```bash
python3 downloader.py backup \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --workers 4
```

### Profile: Export health summary JSON
```bash
python3 downloader.py backup \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --summary-file ./reports/backup-summary.json
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
- Summary file export includes per-mode duration totals and failure counters.

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

## Failure Notification Guidance
- Alert on non-zero exit codes in cron/systemd wrappers.
- Emit JSON logs (`--log-format json --log-file ...`) and feed them to your log stack.
- Send notifications on failures, for example:
  ```bash
  python3 downloader.py backup --config ./profiles/full.toml || curl -X POST -H 'Content-type: application/json' --data '{"text":"Repo-Downloader backup failed"}' https://hooks.slack.com/services/XXX/YYY/ZZZ
  ```
- Validate notification pipeline quarterly with a forced-failure drill.

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
- Keep snapshot root on durable storage when snapshot export is enabled.
- Run retention first with `--dry-run` to verify planned deletions.
- Use `--resume` only for reruns that should continue the same provider/mode/filter signature.
- Start with `--workers 2` and scale gradually based on network and provider API limits.
- Avoid deleting existing backup paths outside planned retention procedures.
- Preserve mirrors as source-of-truth backup artifacts.
- Never run two jobs against the same provider/output root concurrently.
- Use `--force-lock` only when an existing lock is stale or intentionally superseded.
- Keep provider runs separate if needed; pathing is deterministic by provider under `<output>/<provider>/`.

## Future Operational Enhancements
Future operational work items are tracked in:
- `docs/FUTURE_STEPS.md`
- `docs/FEATURE_CATALOG.md`
