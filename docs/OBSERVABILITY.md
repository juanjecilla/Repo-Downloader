# Observability

This document defines coverage and runtime error observability for the CLI.

## Coverage and Codecov

## Coverage Artifacts

- Coverage config file: `.coveragerc`.
- CI output file: `coverage.xml`.

## Codecov Policy

- Patch coverage hard gate: >= 90%.
- Project coverage gate: informational (soft).

Implications:
- Pull requests fail when changed lines fall below 90% coverage.
- Overall project trend is visible but does not block merges initially.

## CI Upload Behavior

- Coverage upload occurs in CI after tests pass.
- Upload must include report generated from current commit.
- Codecov status checks should be required in branch protection once stable.

## Sentry (CLI Error Monitoring)

## Enablement

Sentry is disabled by default.
It is enabled only when DSN is configured.

Environment contract:
- `REPO_DOWNLOADER_SENTRY_DSN`
- `REPO_DOWNLOADER_SENTRY_ENVIRONMENT`
- `REPO_DOWNLOADER_SENTRY_RELEASE`

## Capture Scope

- Capture unhandled exceptions in command execution.
- Capture severe operational failures where error context helps diagnosis.
- Do not capture expected control-flow events as errors.

## Privacy and Redaction

- Apply redaction before sending events.
- Remove or mask token/password/secret-like fields.
- Do not attach raw secrets or auth prompt input.

## CLI Telemetry Boundaries

- Error monitoring only by default.
- Performance tracing disabled by default.
- Tag events with low-cardinality metadata only:
  - provider
  - command
  - mode
  - run_id

## Operational Troubleshooting

When Codecov fails:
1. Inspect patch-level uncovered lines.
2. Add targeted tests.
3. Re-run CI.

When Sentry missing data:
1. Confirm DSN/env vars are set.
2. Confirm command path initializes Sentry.
3. Confirm redaction hook does not drop entire event payload.

When Sentry noise is high:
1. Tighten capture points.
2. Reduce duplicate errors.
3. Improve exception classification and message grouping.
