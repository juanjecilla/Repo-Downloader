## Summary
<!-- What problem does this PR solve? Keep it short and concrete. -->

## Scope
<!-- What is in scope and explicitly out of scope? -->
- In scope:
- Out of scope:

## Key Changes
<!-- List the highest-impact changes only (CLI/API behavior, data flow, storage layout). -->
1.
2.
3.

## Human Review Focus
<!-- Prioritize what a reviewer should verify first. -->
1. **Behavior correctness**
   - Are new/changed user-visible behaviors correct and documented?
2. **Risk of regression**
   - Which existing flows are most likely impacted?
3. **Error handling and failure modes**
   - Are error paths deterministic and actionable?
4. **Security and secrets**
   - Any chance of logging or exposing sensitive values?
5. **Operational impact**
   - Any CI/runtime/performance/storage implications?

## CLI / Interface Changes
<!-- Include flags, defaults, output shape changes, exit codes, paths, contracts. -->
- Added:
- Changed:
- Removed:
- Compatibility notes:

## Evidence
<!-- Add commands and relevant output snippets proving behavior. -->
### Automated tests
```bash
# paste exact commands run
```

### Manual validation
```bash
# paste exact commands run
```

## Files To Review First
<!-- Direct reviewer to the most important files. -->
1.
2.
3.

## Risks and Mitigations
<!-- Call out known risks and what mitigates each one. -->
- Risk:
  - Mitigation:

## Follow-ups
<!-- Link deferred items or next feature IDs from docs/FEATURE_CATALOG.md. -->
- 

## Checklist
- [ ] I updated docs for any user-visible behavior changes.
- [ ] I added/updated tests for the changed behavior.
- [ ] I verified no secrets/tokens are logged.
- [ ] I considered backward compatibility and migration impact.
