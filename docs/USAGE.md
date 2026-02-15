# Usage Guide

## Prerequisites
- Python 3.8+
- `git` installed and available in `PATH`
- SSH key configured for repository access
- Provider credentials:
  - Bitbucket app password.
  - GitHub personal access token (classic or fine-grained with repository read access).
  - GitLab personal access token with API read access.

Install dependencies:
```bash
python3 -m pip install -r requirements.txt
```

## Authentication
Repo-Downloader uses a token/app-password value for API authentication.

Options:
1. Interactive prompt (default fallback).
2. Environment variable via `--token-env`.

Example:
```bash
export BITBUCKET_APP_PASSWORD="***"
python3 downloader.py --provider bitbucket --username my-user --token-env BITBUCKET_APP_PASSWORD
```

If `--token-env` is provided but not set, the CLI falls back to interactive prompt.

## CLI Reference
```bash
python3 downloader.py [command] [options]
```

Commands:
- `backup` (default): run backup sync flow.
- `list-backups`: list discovered mirror/working backup paths.
- `validate-restore`: clone a backup locally and verify refs are readable.

### Options
- `-u, --username`: Remote account username.
- `command`: Optional command (`backup`, `list-backups`, `validate-restore`), default `backup`.
- `--provider`: Provider backend (`bitbucket`, `github`, `gitlab`), default `bitbucket`.
- `--mode`: Backup mode (`mirror`, `working`, `both`), default `both`.
- `-w, --workspace`: Optional workspace filter.
- `--output-dir`: Backup root directory, default `./backups`.
- `--snapshot-format`: Optional mirror snapshot export format (`zip`, `tar.gz`).
- `--snapshot-dir`: Snapshot archive root directory, default `./snapshots`.
- `--include-archived`: Include archived repositories.
- `--dry-run`: Show actions without cloning/fetching/checking out.
- `--ssh-key-path`: SSH private key path, default `~/.ssh/id_rsa`.
- `--role`: Provider role filter, default `member` (Bitbucket only).
- `--token-env`: Environment variable containing token/app-password.
- `--log-format`: Log format (`text` or `json`), default `text`.
- `--log-file`: Optional file path where logs are written in the selected format.
- `--include`: Include repository full-name glob patterns. Repeat or comma-separate values.
- `--exclude`: Exclude repository full-name glob patterns. Repeat or comma-separate values.
- `--branch`: In working mode, include only specific branch names. Repeat or comma-separate values.
- `--branch-pattern`: In working mode, include branches matching glob patterns.
- `--default-branch-only`: In working mode, checkout only the repository default branch.
- `--repo-retries`: Additional retries per repository after a failure, default `0`.
- `--force-lock`: Replace an active/stale run lock for the selected provider/output root.
- `--retain-days`: Delete snapshot/working artifacts older than this many days.
- `--retain-count`: Keep only the most recent N snapshot/working artifacts per repository.
- `--backup-path`: Backup path used by `validate-restore`.
- `--restore-dir`: Clone target used by `validate-restore`, default `./restore-validation`.

## Provider Behavior Matrix
| Capability | Bitbucket | GitHub | GitLab | Notes |
|---|---|---|---|---|
| `--provider` runtime support | Yes | Yes | Yes | All providers implement contract methods. |
| Workspace filter (`--workspace`) | Yes | Yes | Yes | Bitbucket workspace, GitHub organization, GitLab group/namespace. |
| Role filter (`--role`) | Yes | Ignored | Ignored | `--role` only affects Bitbucket permission API. |
| Include/exclude repo filters | Yes | Yes | Yes | Applied in downloader layer against `workspace/repo` full name. |
| Archived repo filtering | Yes | Yes | Yes | Uses provider-specific archive flags normalized by downloader. |
| Branch selectors in working mode | Yes | Yes | Yes | `--branch`, `--branch-pattern`, `--default-branch-only`. |
| Mirror + working output layout | Yes | Yes | Yes | Paths stay `<output>/<provider>/<workspace>/<repo>...`. |
| Dry-run behavior | Yes | Yes | Yes | Planned clone/fetch/checkout actions are logged without git writes. |

## Backup Modes
### `mirror`
- Creates or updates bare mirror repositories.
- Best for disaster recovery and preserving all refs/history.

### `working`
- Creates or updates working-copy clones.
- Fetches and iterates provider branches to checkout/update local branches.

### `both`
- Runs `mirror` and `working` for every repository.

## Output Structure
Given:
- `--output-dir ./backups`
- `--provider bitbucket`
- workspace `acme`
- repository `api-service`

Results:
- Mirror: `./backups/bitbucket/acme/api-service.git`
- Working: `./backups/bitbucket/acme/api-service/`

## Examples
### Mirror-only backup for one workspace
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --mode mirror \
  --workspace acme
```

### Full backup without prompt using env token
```bash
export BITBUCKET_APP_PASSWORD="***"
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --output-dir ./backups
```

### GitHub backup for all accessible repositories
```bash
export GITHUB_TOKEN="***"
python3 downloader.py \
  --provider github \
  --token-env GITHUB_TOKEN \
  --mode both \
  --output-dir ./backups
```

### GitLab backup for one group/namespace
```bash
export GITLAB_TOKEN="***"
python3 downloader.py \
  --provider gitlab \
  --token-env GITLAB_TOKEN \
  --workspace acme-group \
  --mode both \
  --output-dir ./backups
```

### Dry run preview
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --mode both \
  --workspace acme \
  --dry-run
```

### JSON logs to file
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --log-format json \
  --log-file ./logs/backup-run.jsonl
```

### Filter repositories with include/exclude patterns
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --include "acme/*" \
  --exclude "acme/private-*"
```

Filtering semantics:
- Include patterns are applied first. If any include pattern is provided, a repository must match at least one.
- Exclude patterns are applied second. Any exclude match skips the repository.
- Pattern matching runs against repository full names (`workspace/repo`).

### Select working-mode branches
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode working \
  --branch "main,release" \
  --branch-pattern "hotfix/*"
```

Branch selector semantics:
- Selectors apply only in `working` mode.
- If selectors are omitted, all provider branches are considered.
- `--default-branch-only` takes precedence over `--branch` and `--branch-pattern`.

### Retry failed repositories
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --repo-retries 2
```

Retry semantics:
- The command attempts each repository once, plus `--repo-retries` additional attempts.
- Failure classification counters are included in the run summary (`api`, `auth`, `clone`,
  `fetch`, `checkout`, `other`).

### Export mirror snapshots
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode mirror \
  --snapshot-format tar.gz \
  --snapshot-dir ./snapshots
```

Snapshot semantics:
- Snapshots are exported after mirror sync completes for each repository.
- Snapshot path format:
  - `./snapshots/<provider>/<workspace>/<repo>-<timestamp>.<zip|tar.gz>`

### Apply retention policy
```bash
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode mirror \
  --snapshot-format zip \
  --snapshot-dir ./snapshots \
  --retain-days 30 \
  --retain-count 20
```

Retention semantics:
- `--retain-days` deletes artifacts older than the given number of days.
- `--retain-count` keeps only the newest N artifacts for the repository.
- Use `--dry-run` to review planned deletions before applying them.

### List known backup artifacts
```bash
python3 downloader.py list-backups --output-dir ./backups
```

### Validate restore from a mirror backup
```bash
python3 downloader.py validate-restore \
  --backup-path ./backups/bitbucket/acme/api-service.git \
  --restore-dir /tmp/api-service-restore
```

### Run locking
Each run acquires a lock file under the output root:
- `<output>/.repo-downloader-<provider>.lock`

If another process is active for the same provider/output root, the run exits with an error.
Use `--force-lock` only when you are sure the existing lock is stale or should be replaced.

## Restore Notes
- Mirror restore:
  ```bash
  git clone /path/to/repo.git restored-repo
  ```
- Working copy backups are directly browsable as regular repositories.

## Known Limitations
- Provider behaviors can differ based on token scopes and provider-side permissions.

## Exit Codes
- `0`: Completed without repository failures.
- `1`: Startup/provider/auth configuration failure.
- `2`: Completed with one or more repository processing failures.
- `130`: Interrupted by user.
