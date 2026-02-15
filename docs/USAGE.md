# Usage Guide

## Prerequisites
- Python 3.8+
- `git` installed and available in `PATH`
- SSH key configured for repository access
- Bitbucket app password (for current production provider support)

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
python3 downloader.py [options]
```

### Options
- `-u, --username`: Remote account username.
- `--provider`: Provider backend (`bitbucket`, `github`, `gitlab`), default `bitbucket`.
- `--mode`: Backup mode (`mirror`, `working`, `both`), default `both`.
- `-w, --workspace`: Optional workspace filter.
- `--output-dir`: Backup root directory, default `./backups`.
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

## Restore Notes
- Mirror restore:
  ```bash
  git clone /path/to/repo.git restored-repo
  ```
- Working copy backups are directly browsable as regular repositories.

## Known Limitations
- GitHub and GitLab providers are currently stubs and intentionally return not-implemented status.

## Exit Codes
- `0`: Completed without repository failures.
- `1`: Startup/provider/auth configuration failure.
- `2`: Completed with one or more repository processing failures.
- `130`: Interrupted by user.
