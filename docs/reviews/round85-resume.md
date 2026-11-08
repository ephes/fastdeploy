# Round 85 B22 resume note

Status: implemented, unmerged, review and full local checks blocked. Parked at the
owner's explicit instruction after OAuth failure. Do not merge until the review
and all required local checks pass. No deployments, PRs, tags, releases or Actions
were run. Only this parking branch is pushed.

Base: origin/main d33be9803769a7d31b62570e44ca26e7d534df5f (re-fetched before parking).
All three scout findings were still present; none were skipped. Same-file/docs
bundle order:

1. `fastdeploy-runtime-token-lifetime-invariant`: startup requires token seconds
   >= runtime + 2731 (30 seconds teardown, two maximum 1350-second final reporting
   sequences, one second JWT rounding). Runner/admission share limits; defaults
   unchanged. Open-step classification retains its existing token-lifetime guard.
2. `fastdeploy-config-duplicate-key-refusal`: JSON public pairs hook and a narrow
   SafeLoader subclass reject repeated nested mapping keys and YAML merge
   collisions, retaining ordinary aliases within existing budgets.
3. `fastdeploy-service-definition-semantic-preflight`: validate optional script
   paths and step objects/names before sync; keep extension fields/defaults and
   validate playbook-derived steps. Invalid snapshots emit no service events and
   leave stored services intact, including with force enabled.

README, deployment documentation and Unreleased changelog are updated.

## Validation

- Final `tests/unit/deployment_admission_test.py` run on unchanged main:
  **31 failed, 1 passed**. The pass covers preserved extension/alias support.
- Targeted tests: **110 passed** using
  `uv run --frozen pytest -q tests/unit/deployment_admission_test.py tests/unit/time_settings_test.py tests/unit/service_config_admission_test.py tests/unit/tasks_retry_settings_test.py`.
- `just lint`: pass. `just typecheck`: pass (35 source files).
- Full `just test-python -q --tb=short` attempt: **649 passed, 194 database setup
  errors**. These errors prevent a full-suite pass. PostgreSQL 17 `initdb` for a
  fresh workspace-local test cluster failed at `shmget` with Operation not
  permitted; the test database was unavailable. No existing DB was accessed.
  The targeted run includes the subsequently added merge/name admission cases.
- Frontend `npm ci --ignore-scripts`, `npm test`: **125 passed**, and
  `npm run build`: pass.
- `npm run test:browser`: blocked at Chromium launch: sandbox denies
  `bootstrap_check_in ... MachPortRendezvousServer` (Permission denied 1100).
  The existing login test could not execute.
- Opus review via claude-review-loop, model `claude-opus-5-5`, effort `high`:
  **PROVIDER_ERROR**, not a verdict. Exact cause: "Failed to authenticate: OAuth
  session expired and could not be refreshed". No completed review rounds or
  findings; no subagents. Bundle omissions/redactions/truncations were empty.

## Continue

Restore Claude OAuth through the normal login flow, then run the installed
claude-review-loop harness on this branch with model `claude-opus-5-5`, effort
`high`. Review the complete implementation delta against the base above (the
changes are committed for parking, so a plain worktree review would be empty).
Use a writable review checkout with the implementation applied as uncommitted
changes, or pass `--baseline-ref` for that base. Continue repairs/review while
findings shrink, stopping at four rounds or a repeated required finding.

Run all local checks in an environment allowing a **fresh synthetic** PostgreSQL
cluster and Chromium. Use synthetic SECRET_KEY/PATH_FOR_DEPLOY and an explicitly
selected throwaway DATABASE_URL. Never use host deployment commands, live records,
or GitHub Actions to substitute for these checks. Cache overrides used here:
UV_CACHE_DIR=<workspace>/.cache/uv, UV_TOOL_DIR=<workspace>/.cache/uv-tools,
npm_config_cache=<workspace>/.cache/npm. Review artifacts remain locally at
<workspace>/reviews/round1; full check logs are at <workspace>/*-tests.log,
<workspace>/python-full.log and <workspace>/frontend-build.log.

Only after a clean/suggestion-only review and complete local gates: fetch origin;
if main moved, rebase onto origin/main and rerun checks; merge locally with
--no-ff into main, run full local checks again, then push main and verify its SHA
with git ls-remote. Never delete remote branches. No PRs, deploys, releases/tags,
feature pushes except parking, Actions use or work-app writes.
