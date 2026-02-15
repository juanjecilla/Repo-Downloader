# AGENTS.md

## Purpose
This repository maintains a backup CLI for remote repositories.
Future development should follow feature IDs and docs in `docs/`.

## Source of Truth
- Feature backlog: `docs/FEATURE_CATALOG.md`
- Sequenced rollout plan: `docs/FUTURE_STEPS.md`
- Execution/file map: `docs/AGENT_IMPLEMENTATION_GUIDE.md`
- Compatibility contract: `utils/compatibility.py`
- CI matrix and gates: `.github/workflows/pylint.yml`
- User docs affected by behavior changes:
  - `docs/USAGE.md`
  - `docs/OPERATIONS.md`

## Development Workflow For Agents
1. Choose exactly one feature ID from `docs/FEATURE_CATALOG.md`.
2. Create a dedicated git worktree from `develop`.
3. Use a feature branch name:
   - Preferred general format: `feature/<feature-id>-<short-name>`
   - In Codex sessions, use `codex/feature/<feature-id>-<short-name>` when required by environment rules.
4. Implement code + tests + docs in the worktree.
5. Run at minimum:
   - `python3 -m unittest discover -s tests -p "test_*.py"`
   - `python3 -m unittest tests/test_compatibility.py`
6. Update docs impacted by the feature.
7. Update feature status in `docs/FEATURE_CATALOG.md`.
8. Open a PR:
   - Independent feature: target `develop`.
   - Dependent feature in an active stack: target the immediate parent feature branch to avoid
     duplicate diffs.

## Logging and Security Expectations
- Never log token values, secrets, or raw sensitive paths.
- Prefer structured events for operational behavior.
- Include redaction tests when adding new logging fields.

## Compatibility Guardrails
- Keep runtime checks aligned with `utils/compatibility.py`.
- Keep README/USAGE compatibility matrix in sync with CI test matrix entries.

## Scope Guardrails
- Keep changes scoped to the selected feature ID.
- Do not silently change CLI behavior without documentation updates.
- If a feature requires follow-up work, record it in `docs/FEATURE_CATALOG.md`.
