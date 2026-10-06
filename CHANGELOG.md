Unreleased
==========

### Features
- `python commands.py issueservicetoken --service S --user U --days N [--origin O]` issues a recorded,
  revocable service token (with `jti`) from the command line, so playbooks and operators can replace
  legacy tokens without a web login. `--days` is capped by `SERVICE_TOKEN_MAX_EXPIRE_DAYS`; the user
  and the service must exist. Only the token is printed on stdout (its `jti` and expiry go to stderr);
  a refusal exits with status 1. See the legacy token cutover in [docs/auth.md](docs/auth.md).
- Single-flight deployments per service: `POST /deployments/` returns `409 Conflict` with the running
  deployment id while the service already has an active deployment, instead of spawning a second
  concurrent deploy. Check and insert are serialized by a database row lock on the service, orphaned
  deployments of the service do not block (they are finished as failed as part of a successful start), and deployments older than the deployment token
  lifetime no longer block. Addresses the per-service limit from security review #07.

### Bug Fixes
- A services sync (`POST /services/sync`, `commands.py syncservices`) no longer wipes the
  deployment history when the services directory is empty or mis-pointed: it is refused (409 /
  exit status 1, nothing changed) when no services are found while the database has some, or when
  more than half of the services would be deleted, unless `force` (`?force=true` / `--force`) is
  given. Services with a running deployment are never deleted and are reported as skipped. The
  response and CLI output list the updated, deleted and skipped services. Deploy note: the Ansible
  deploy runs `syncservices`, so a deploy with an empty or mostly removed services directory now
  fails at that task instead of deleting the services.
- The web frontend shows a refused services sync (409) instead of only logging it: the refusal
  message and the services that would be deleted are displayed, with a "force sync" button that
  retries with `force=true` after confirmation. Other sync failures are shown as well.
- The deploy task no longer leaves a deployment "active" (blocking new deploys of the service until the deployment
  token expires) after a network error while reporting: posting a step retries connection errors and `5xx` with
  exponential backoff and never aborts reading the deploy script output, a step that cannot be reported is logged to
  stderr instead of being dropped silently, output lines that are not a JSON object are skipped, finishing the
  deployment has its own retries, and a failure there no longer replaces the original deploy error. A failed deploy
  whose failure step cannot be reported is not finished as an apparent success. A non-string `error_message` (for example an Ansible `msg` list) is
  converted to text instead of being rejected with 422.
- Orphaned deployments are no longer recorded as successful. A deploy whose script failed after every step was
  already reported as successful, while the API was unreachable for the failure step, used to be finished by the
  orphan cleanup and then looked successful. The orphan cleanup (on `GET /deployments/`,
  `GET /deployments/{deployment_id}` and a successful start of the same service) now finishes such deployments as
  failed: it adds a `deployment orphaned` step with state `failure` whose message records the reason. The step is
  returned by the API with the other steps, broadcast over the websocket and shown as a failed step in the web
  frontend; a late finish from the deploy task does not change it, and it is not copied into the step list of the
  next deployment. `DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS` now counts from the latest activity (deployment start
  or last step start/finish) instead of only the start, so a long deployment whose task is still retrying to finish
  it is not finished early; until then it keeps blocking new deploys of the service and services sync keeps the
  service. The cleanup re-checks a deployment under the service lock and a row lock on the deployment before
  finishing it; finishing a deployment and processing a step take the same deployment row lock, so a deploy task
  finishing concurrently is never marked as orphaned.

### Security
- `GET /deployments/{deployment_id}` checks that the deployment belongs to the token's service before
  reconciling an orphaned deployment, so a service token can no longer finish another service's
  deployment by reading it. A deployment of another service now returns the same `404 Deployment not
  found` as an unknown id (was `403 Wrong service token`), so the endpoint no longer reveals which ids
  exist. `GET /steps/?deployment_id=` returns 404 instead of 500 for an unknown deployment.
- Websocket authentication hardening (`/deployments/ws/{client_id}`): any failed authentication
  (including a valid service, deployment or config token, or a token for a deleted user) now sends
  an authentication failure and closes the connection (code `1008`) instead of leaving it
  registered. Connection cleanup runs on every exit path, so rejected or server-closed sockets no
  longer accumulate in memory.
- A client id that is still connected can no longer be taken over: a second connection with the
  same id is refused, the id is bound to the authenticated user for the connection's lifetime
  (re-authenticating as another user closes the connection), and the "client left" broadcast no
  longer includes the client id. Only authenticated connections receive or trigger broadcasts.
- Service tokens can be revoked. Every issued service token carries a `jti` claim and is recorded
  in the new `service_token` table (service, origin, user, issue/expiry time, revocation time).
  Unknown or revoked token ids and tokens of deleted users are rejected with 401. Revoke via
  `DELETE /service-token/{jti}` or `python commands.py revokeservicetoken <jti>`; list with
  `python commands.py listservicetokens`. `POST /service-token` now also returns `jti` and
  `expires_at`. The maximum lifetime is lowered from 180 to 90 days (`SERVICE_TOKEN_MAX_EXPIRE_DAYS`)
  and the web frontend now suggests 7 instead of 30 days.
- Deploy note: legacy service tokens without `jti` (all tokens issued before this release, e.g. in
  CI secrets) are rejected unless `LEGACY_SERVICE_TOKENS_ACCEPTED_UNTIL` is set (ISO 8601) to give
  a time-limited transition window. The `service_token` table is created automatically on startup
  (`create_all`), no manual migration is needed.
- Each connection has at most one session expiry timer; re-authentication replaces it and
  disconnecting cancels it, so stale timers no longer close re-authenticated sessions or a newer
  connection reusing the id.
- Service token records no longer accumulate: records of tokens that expired or were revoked more
  than `SERVICE_TOKEN_RETENTION_DAYS` (default 30) days ago are deleted whenever a service token is
  issued, and on demand with `python commands.py purgeservicetokens [--older-than-days N]`.


### Development
- GitHub Actions CI (`.github/workflows/ci.yml`) runs `just lint`, `just typecheck` and the
  pytest suite against a `postgres:17` service container, plus the frontend Vitest suite and
  build, on every branch push and on pull requests. Actions are pinned by commit SHA, permissions
  are read-only and no secrets are used.
- The stale, manual-only `deploy.yml` workflow is removed. It posted to the staging deploy API
  with an unpinned third-party action and echoed the response through a shell line (a script
  injection pattern); deploys go through the Ansible playbooks.
- The test configuration only sets `DATABASE_URL` as a default, so it can be overridden from the
  environment (CI uses this to reach its service container).
- The Python test suite runs on a clean checkout without a frontend build: the test setup creates
  the git-ignored `frontend/dist` directory that the app mounts at import time.
- `just lint` / `just lint-fix` run the pinned ruff 0.14.0 via `uvx` (same version as the
  pre-commit hook) instead of expecting ruff in the virtualenv, and the code base is lint- and
  format-clean. FastAPI `Depends`/`Query` defaults are whitelisted for bugbear's B008. Domain
  models no longer share mutable default arguments (`context`, `steps`, `data`, `config`) between
  instances, and the service cascade test now actually asserts that deployments are deleted.

0.2.0 - 2025-09-01
==================

### Major Changes
- **Python Packaging**: Migrated to hybrid src layout with UV build backend
  - Backend code moved to `src/deploy/` following Python best practices
  - Frontend remains at root level to maintain JavaScript conventions
  - Package imports remain unchanged (`from deploy import ...`)
- **Frontend Testing**: Migrated from Jest to Vitest for better Vite integration
- **Python 3.13 Support**: Full compatibility with Python 3.13
- **Developer Experience**: Added comprehensive justfile for task automation
- **Code Quality**: Migrated from black/isort/flake8 to ruff for faster, unified linting

### Features
- Add justfile with comprehensive development commands
- Add support for Python 3.12 and 3.13
- Switch to UV for dependency management and lockfile handling
- Add deployment convenience commands to CLI
- Add CLAUDE.md for AI assistant instructions
- Frontend dependencies updated to latest versions (Vite 7.1, Vue 3.5, TypeScript 5.9)

### Refactoring
- Migrate to Pydantic v2 patterns (ConfigDict, model_dump, etc.)
- Migrate to hybrid src layout for better Python packaging
- Replace black/isort/flake8 with ruff
- Update all datetime.utcnow() to datetime.now(datetime.UTC)
- Modernize test fixtures for pytest-asyncio 1.1.0+

### Bug Fixes
- Fix httpx 0.28+ compatibility in e2e tests
- Fix pytest-asyncio 1.1.0 compatibility issues
- Fix UV build backend configuration for package name mismatch
- Fix pydantic URL validation from Starlette
- Update all Jest references to Vitest

### Documentation
- Comprehensive README update with current setup instructions
- Add project structure documentation
- Update MkDocs documentation for current project state
- Add CLI documentation for new commands
- Document trunk-based development workflow

### Dependencies Updates
- **Backend**: FastAPI 0.115+, SQLAlchemy 2.0+, Pydantic 2.0+, httpx 0.27+
- **Frontend**: Vite 7.1, Vue 3.5, TypeScript 5.9, Pinia 3.0
- **Testing**: pytest-asyncio 0.24+, Vitest (replacing Jest)
- **Build**: UV 0.8.14+ with uv_build backend

### Development Infrastructure
- Pre-commit hooks configuration with ruff and mypy
- Support for UV package management
- Improved Docker and deployment configurations
- Environment variable handling for tests

0.1.2 - 2022-03-21
===================

### Features
- use mixin to raise events after uow context manager exits
    - #9 issue by @ephes

### Refactoring
- increase coverage for adapters/filesystem.py
    - #22 issue by @ephes
- refactor command handlers
    - #18 issue by @ephes
- improve message bus dependency
    - #13 issue by @ephes
- use the same `get_user_by_name` function everywhere
    - #10 issue by @ephes
- use own message bus to sync services during deployment
    - #8 issue by @ephes
- fix repository method names
    - #6 issue by @ephes

### Fixes
- exception in `run_task` on long output
    - #24 issue by @ephes
- delete deployments and steps from frontend after service deleted event
    - #11 issue by @ephes

0.1.1 - 2022-02-29
==================

### Features
- add CHANGELOG.md
    - #3 - add CHANGELOG.md by @ephes

### Fixes
