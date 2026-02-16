# Usage Guide

## Prerequisites
- Python 3.8+
- `git` installed and available in `PATH`
- SSH key configured for repository clone access
- Provider credentials:
  - Bitbucket app password
  - GitHub personal access token
  - GitLab personal access token

Install dependencies for source execution:
```bash
python3 -m pip install -r requirements.txt
```

Install from source with `pipx`:
```bash
pipx install .
```

Install from PyPI:
```bash
python3 -m pip install --upgrade repo-downloader
```

## Compatibility Matrix
| Component | Support Level | Versions / Notes |
|---|---|---|
| Operating system | CI-tested | Ubuntu (`ubuntu-latest`), macOS (`macos-latest`), Windows (`windows-latest`) |
| Python runtime | Supported | Minimum `3.8` |
| Python runtime | CI-tested | `3.9`, `3.11`, `3.12` |
| Git CLI | Supported | Minimum `2.30.0` |
| Providers | Supported | Bitbucket, GitHub, GitLab |

## Authentication
Repo-Downloader supports three token sources for backup flows.

Resolution precedence:
1. `--token-env`
2. Auth profile from keyring (`--auth-profile`)
3. Interactive prompt fallback

Use auth command for profile-based credential setup:
```bash
repo-downloader auth github
repo-downloader auth bitbucket --profile work
repo-downloader auth gitlab --status
repo-downloader auth github --logout
```

Bitbucket username resolution:
1. `--username`
2. Stored profile username
3. Prompt fallback

## CLI Reference
Source entrypoint:
```bash
python3 downloader.py [command] [options]
```

Packaged entrypoint:
```bash
repo-downloader [command] [options]
```

Commands:
- `backup` (default): run backup sync flow
- `list-backups`: list discovered mirror/working backup paths
- `validate-restore`: clone a backup and verify refs are readable
- `auth`: configure/validate/remove provider credentials in auth profiles

### Primary Options
- `-u, --username`: remote account username (required for Bitbucket if not in profile)
- `--config`: path to TOML/YAML profile file
- `--provider`: provider backend (`bitbucket`, `github`, `gitlab`)
- `--mode`: backup mode (`mirror`, `working`, `both`)
- `-w, --workspace`: workspace filter
- `--output-dir`: backup root directory
- `--snapshot-format`: optional snapshot export format (`zip`, `tar.gz`)
- `--snapshot-dir`: snapshot root directory
- `--include-archived`: include archived repositories
- `--dry-run`: show planned actions without git writes
- `--ssh-key-path`: SSH private key path
- `--role`: Bitbucket role filter
- `--token-env`: token/app-password environment variable name
- `--auth-profile`: auth profile name for keyring lookup (default `default`)
- `--log-format`: `text` or `json`
- `--log-file`: optional log file path
- `--summary-file`: optional run summary JSON output
- `--include`, `--exclude`: repository include/exclude glob patterns
- `--branch`, `--branch-pattern`, `--default-branch-only`: branch selectors (working mode)
- `--repo-retries`: retries per repository
- `--workers`: concurrent repository workers
- `--force-lock`: replace existing run lock
- `--retain-days`, `--retain-count`: retention controls
- `--resume`: resume from checkpoint

### Restore Command Options
- `--backup-path`: backup path for `validate-restore`
- `--restore-dir`: restore target directory

### Auth Command Options
- `--profile`: auth profile name (default `default`)
- `--status`: validate and print profile auth status
- `--logout`: delete stored credential/profile
- `--no-open-browser`: do not open provider credential setup URL

### Sentry Options (optional overrides)
- `--sentry-dsn`
- `--sentry-environment`
- `--sentry-release`

## Provider Behavior Matrix
| Capability | Bitbucket | GitHub | GitLab | Notes |
|---|---|---|---|---|
| Runtime provider support | Yes | Yes | Yes | All providers implement contract methods |
| Workspace filter | Yes | Yes | Yes | Workspace/org/group semantics vary by provider |
| Role filter (`--role`) | Yes | Ignored | Ignored | Bitbucket only |
| Include/exclude repo filters | Yes | Yes | Yes | Applied in downloader layer |
| Branch selectors | Yes | Yes | Yes | Working mode only |
| Auth profile support | Yes | Yes | Yes | Via keyring profile storage |

## Examples

### Backup from environment token
```bash
export BITBUCKET_APP_PASSWORD="***"
repo-downloader backup \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --mode both \
  --output-dir ./backups
```

### Backup from stored auth profile
```bash
repo-downloader auth github --profile personal
repo-downloader backup --provider github --auth-profile personal --mode both
```

### Auth status and logout
```bash
repo-downloader auth gitlab --profile work --status
repo-downloader auth gitlab --profile work --logout
```

### Config-driven run
```bash
repo-downloader backup --config ./profiles/daily.toml
```

Example `daily.toml`:
```toml
[backup]
provider = "bitbucket"
mode = "both"
workspace = "acme"
output_dir = "./backups"
snapshot_format = "zip"
snapshot_dir = "./snapshots"
retain_days = 30
retain_count = 20
resume = true
include = ["acme/*"]
exclude = ["acme/private-*"]
auth_profile = "default"
```

## Observability

Codecov:
- CI uploads `coverage.xml`.
- Patch coverage has a hard gate at `90%`.
- Project coverage is informational.

Sentry:
- Disabled by default.
- Enabled only when DSN is configured.
- Environment contract:
  - `REPO_DOWNLOADER_SENTRY_DSN`
  - `REPO_DOWNLOADER_SENTRY_ENVIRONMENT`
  - `REPO_DOWNLOADER_SENTRY_RELEASE`

Example:
```bash
export REPO_DOWNLOADER_SENTRY_DSN="https://<key>@o0.ingest.sentry.io/0"
export REPO_DOWNLOADER_SENTRY_ENVIRONMENT="production"
repo-downloader backup --provider github --auth-profile default --mode mirror
```

## Run Locking
Lock path:
- `<output>/.repo-downloader-<provider>.lock`

If another process is active for the same provider/output root, run exits with error.
Use `--force-lock` only for stale or intentionally superseded runs.

## Exit Codes
- `0`: completed without repository failures
- `1`: startup/provider/auth/configuration failure
- `2`: completed with one or more repository failures
- `130`: interrupted by user
