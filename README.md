# Repo-Downloader

Repo-Downloader is a Python CLI tool for backing up remote repositories, with Bitbucket support hardened for repeatable backups.

## Features
- Provider-aware CLI (`bitbucket`, `github`, `gitlab`).
- Backup modes:
  - `mirror`: bare mirror repositories for full history/ref backup.
  - `working`: normal working copies with branch checkout.
  - `both`: run mirror and working backups in one pass.
- Workspace filtering and optional archived-repository inclusion.
- Auth profiles via `repo-downloader auth <provider>` with keyring-backed secret storage.
- Non-interactive auth via environment variable (`--token-env`) with profile/prompt fallback.
- Deterministic output layout under `./backups` by default.
- Dry-run mode to preview changes before cloning/fetching.
- Branch selection controls for working-mode checkout (`--branch`, `--branch-pattern`, `--default-branch-only`).
- Include/exclude repository filtering with glob patterns (`workspace/repo`).
- Per-repository retries with failure classification summary (`--repo-retries`).
- Run lock protection to prevent overlapping runs (`--force-lock` to override).
- Optional mirror snapshot exports (`--snapshot-format zip|tar.gz` and `--snapshot-dir`).
- Optional retention policies for snapshots/working artifacts (`--retain-days`, `--retain-count`).
- Restore helper commands (`list-backups`, `validate-restore`) for inventory and restore drills.
- Checkpoint-based resumable runs (`--resume`) for interrupted backup recovery.
- Config profile support via TOML/YAML (`--config`) with CLI-overrides-config precedence.
- Containerized runtime via Docker (`Dockerfile`) for isolated execution.
- Concurrent repository workers (`--workers`) with deterministic grouped log output.
- JSON summary export (`--summary-file`) with health metrics and duration counters.
- Secret redaction hardening for error/log output across token/password/secret patterns.
- Optional Sentry error monitoring (disabled by default).

## Compatibility Matrix
| Component | Support Level | Versions / Notes |
|---|---|---|
| Operating system | CI-tested | Ubuntu (`ubuntu-latest`), macOS (`macos-latest`), Windows (`windows-latest`) |
| Python runtime | Supported | Minimum `3.8` |
| Python runtime | CI-tested | `3.9`, `3.11`, `3.12` |
| Git CLI | Supported | Minimum `2.30.0` in `PATH` |
| Providers | Supported | Bitbucket, GitHub, GitLab |

Runtime checks:
- `repo-downloader` emits a `runtime.compatibility` structured log event at startup.
- Warnings are emitted when Python/Git/platform are outside the validated matrix.

## Quick Start
1. Install with `pipx` (recommended packaged mode):
   ```bash
   pipx install .
   ```
2. Install from PyPI:
   ```bash
   python3 -m pip install --upgrade repo-downloader
   ```
3. Or install dependencies for source execution:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
4. Create a Bitbucket app password:
   [Bitbucket App Passwords](https://bitbucket.org/account/settings/app-passwords/)
5. Ensure SSH access to repositories is configured.
6. Run:
   ```bash
   repo-downloader --provider bitbucket --username <bitbucket-user> --mode both
   ```
7. Source execution equivalent:
   ```bash
   python3 downloader.py --provider bitbucket --username <bitbucket-user> --mode both
   ```

## Example
```bash
export BITBUCKET_APP_PASSWORD="***"
python3 downloader.py \
  --provider bitbucket \
  --username my-user \
  --token-env BITBUCKET_APP_PASSWORD \
  --workspace my-workspace \
  --mode both \
  --output-dir ./backups
```

## Output Layout
- Mirror repo: `<output>/<provider>/<workspace>/<repo>.git`
- Working copy: `<output>/<provider>/<workspace>/<repo>/`

With default options this becomes:
- `./backups/bitbucket/<workspace>/<repo>.git`
- `./backups/bitbucket/<workspace>/<repo>/`

## Documentation
- Documentation index: `docs/INDEX.md`
- Full usage and CLI reference: `docs/USAGE.md`
- Operations and restore/runbook guidance: `docs/OPERATIONS.md`
- Release policy and workflow runbook: `docs/RELEASING.md`
- Auth profile lifecycle and storage model: `docs/AUTH_PROFILES.md`
- Coverage/Sentry telemetry policy: `docs/OBSERVABILITY.md`
- Current implementation milestones and acceptance gates: `docs/IMPLEMENTATION_PLAN.md`
- Future steps and phased roadmap: `docs/FUTURE_STEPS.md`
- Comprehensive feature catalog for future agents: `docs/FEATURE_CATALOG.md`
- Agent file-map and execution workflow: `docs/AGENT_IMPLEMENTATION_GUIDE.md`
- Repository automation/agent guardrails: `AGENTS.md`

## Testing
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

## Roadmap
Roadmap and future implementation steps were moved to `docs/FUTURE_STEPS.md` and `docs/FEATURE_CATALOG.md`.
