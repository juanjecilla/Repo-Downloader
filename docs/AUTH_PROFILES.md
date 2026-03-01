# Auth Profiles

This document defines the provider auth UX and storage model.

## Goals

- Support `repo-downloader auth <provider>` for cloud providers:
  - `bitbucket`
  - `github`
  - `gitlab`
- Store secrets securely in OS keyring.
- Store non-secret metadata in local config file.
- Preserve existing non-interactive auth behavior (`--token-env`).

## CLI Surface

Command:
- `repo-downloader auth <provider>`

Options:
- `--profile <name>`: profile key, default `default`.
- `--status`: validate and display current profile auth state.
- `--logout`: remove stored credential/profile.
- `--no-open-browser`: do not launch credential setup page.

Backup integration option:
- `--auth-profile <name>`: profile used for token lookup in non-auth commands.

## Credential Lifecycle

Setup flow:
1. User runs `repo-downloader auth <provider>`.
2. CLI prints provider token/app-password guidance.
3. CLI optionally opens provider setup URL.
4. CLI prompts for credential input (and Bitbucket username if needed).
5. CLI validates credential by calling provider user endpoint.
6. On success, credential is saved in keyring and metadata profile is stored locally.

Status flow:
1. Load profile metadata.
2. Resolve keyring secret.
3. Validate with provider API.
4. Display result and resolved user identity.

Logout flow:
1. Remove keyring secret for provider/profile.
2. Remove local profile metadata entry.

## Storage Model

Secret storage:
- Backend: `keyring`.
- Service name: `repo-downloader`.
- Secret key format: `<provider>:<profile>`.
- Stored value: token/app password only.

Metadata storage:
- Backend: local JSON file under `platformdirs` user config path.
- Example path: `<user-config-dir>/repo-downloader/auth-profiles.json`.
- Metadata fields include:
  - `provider`
  - `profile`
  - `username` (Bitbucket required)
  - `user_hint`
  - `created_at`
  - `updated_at`
  - `validated_at`

## Token Resolution Precedence

For backup and other non-auth commands:
1. `--token-env` (if set and present).
2. keyring credential from `--auth-profile` and selected provider.
3. interactive prompt fallback.

Bitbucket username resolution:
1. `--username`.
2. stored profile `username`.
3. interactive prompt.

## Provider Scope Guidance

This phase supports cloud providers only:
- Bitbucket Cloud (`bitbucket.org`)
- GitHub Cloud (`github.com`)
- GitLab SaaS (`gitlab.com`)

Enterprise/self-hosted URLs are intentionally deferred to a future feature.

## Provider Credential Guidance

Bitbucket:
- Credential type: app password.
- Additional required field: account username.

GitHub:
- Credential type: personal access token.

GitLab:
- Credential type: personal access token.

## Security Requirements

- Never print token values.
- Never persist token values in profile JSON.
- Redact secret-looking fields in logs/errors.
- Auth errors must avoid leaking submitted credential text.

## Failure Behavior

- If keyring backend is unavailable, return actionable error guidance.
- If provider validation fails, do not persist credentials.
- If profile exists but secret is missing, return status error and remediation guidance.
