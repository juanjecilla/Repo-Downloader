# Repo-Downloader

Repo-Downloader is a Python CLI tool for backing up remote repositories, with Bitbucket support hardened for repeatable backups.

## Features
- Provider-aware CLI (`bitbucket`, `github`, `gitlab`).
- Backup modes:
  - `mirror`: bare mirror repositories for full history/ref backup.
  - `working`: normal working copies with branch checkout.
  - `both`: run mirror and working backups in one pass.
- Workspace filtering and optional archived-repository inclusion.
- Non-interactive auth via environment variable (`--token-env`) with prompt fallback.
- Deterministic output layout under `./backups` by default.
- Dry-run mode to preview changes before cloning/fetching.
- Branch selection controls for working-mode checkout (`--branch`, `--branch-pattern`, `--default-branch-only`).
- Include/exclude repository filtering with glob patterns (`workspace/repo`).
- Per-repository retries with failure classification summary (`--repo-retries`).
- Run lock protection to prevent overlapping runs (`--force-lock` to override).
- Optional mirror snapshot exports (`--snapshot-format zip|tar.gz` and `--snapshot-dir`).

## Quick Start
1. Install dependencies:
   ```bash
   python3 -m pip install -r requirements.txt
   ```
2. Create a Bitbucket app password:
   [Bitbucket App Passwords](https://bitbucket.org/account/settings/app-passwords/)
3. Ensure SSH access to repositories is configured.
4. Run:
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
