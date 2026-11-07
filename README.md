# fastDeploy

A deployment automation platform that enables both technical and non-technical users to deploy web applications via API or web interface. Features real-time deployment monitoring through WebSockets and manages infrastructure using Ansible playbooks.

## 📚 Full Documentation

**[Read the full documentation on Read the Docs](https://fastdeploy-ephes.readthedocs.io/en/latest/)**

## Requirements

- Python 3.10+ (fully compatible with Python 3.13)
- PostgreSQL client and server tools
- Node.js 24 and npm (for frontend development)
- uv (for Python package management), just, and lsof

## Quick Start

Install Python 3.12 (used by `just install`), uv, just, PostgreSQL client/server
commands (`initdb`, `pg_ctl`, `postgres`, `psql`, `createdb`, `createuser`,
`pg_dump`), lsof, and Node.js 24 with npm. Put these tools on PATH. Run from the
repository root in one shell; the activated environment supplies Honcho and MkDocs.
This sequence assumes a fresh local cluster and free default service ports.

```shell
just install
source .venv/bin/activate
npm --prefix frontend ci
export SECRET_KEY="$(uv run python -c 'import secrets; print(secrets.token_hex(32))')"
export PATH_FOR_DEPLOY="$PATH"
export DATABASE_URL=postgresql+asyncpg:///deploy
just db-init
pg_ctl -D databases/postgres -l databases/postgres.log -w start
just db-create
just createuser
pg_ctl -D databases/postgres -m fast -w stop
just dev
```

`just createuser` prompts for a username and password and creates the application
tables. The exports configure the CLI and development processes in this shell;
for later shells, save the same values in a git-ignored root `.env` (see below).
`PATH_FOR_DEPLOY` is the executable search path passed to deployment subprocesses;
no deployments are needed for setup. Do not run `just syncservices` against real
service data.

Setup PostgreSQL runs only between `pg_ctl start` and `pg_ctl stop`. After the
stop completes, Honcho (`just dev`) owns PostgreSQL and the other development
processes. Press Ctrl+C in that terminal to stop the stack. `just db-start` is an
alternative foreground server for manual work; stop it before `just dev`.

### Rerunning database setup

`just db-init` is first-time only. With PostgreSQL running, `just db-create`
checks catalog existence and creates only missing databases and the `deploy`
role. Connection, permission, dump, and SQL errors fail the command. Only a newly
created `deploy_test` receives a schema-only dump; an existing test database is
never overwritten. Pytest creates its own tables in the test database.
If schema copying fails, inspect the diagnostic: the newly created test database
may be incomplete. Rerunning preserves it; explicitly remove/recreate it only if
it is disposable and you intend to discard it. Never point tests at real data.
The application schema is initialized by `just createuser`, whose reruns preserve
an existing user's password.

## Configuration

### Environment Variables

fastDeploy uses environment variables for configuration. Create a `.env` file in the project root:

```shell
# Required
SECRET_KEY=your-secret-key-here
PATH_FOR_DEPLOY=/path/to/deploy
DATABASE_URL=postgresql+asyncpg:///deploy

# Deployment configuration
DEPLOYMENT_MAX_RUNTIME_SECONDS=1800  # Deploy output/reporting and process exit; finite >0, <=86400 seconds
SUDO_USER=deploy  # User to run deployment scripts as (default: jochen)
DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS=300  # Ignore very new deployments during orphan reconciliation

# Service tokens
SERVICE_TOKEN_ADMIN_USERS='["operator"]'  # Existing users allowed to issue/revoke tokens via API (default [])
RESTORE_POLICIES='{"echoport-backup":{"bucket":"backups","prefixes":["archive/","work_app/"]}}'  # Default {} denies restores
SERVICE_TOKEN_MAX_EXPIRE_DAYS=90  # Longest lifetime a service token can be issued with
# LEGACY_SERVICE_TOKENS_ACCEPTED_UNTIL=2026-11-01T00:00:00+00:00  # Accept tokens without jti until then
SERVICE_TOKEN_RETENTION_DAYS=30  # Delete expired/revoked token records older than this

# Failed login limit on POST /token (429 at the limit; LOGIN_FAILURE_LIMIT=0 turns it off)
LOGIN_FAILURE_LIMIT=10  # failed attempts per user name and client address inside the window
LOGIN_ADDRESS_FAILURE_LIMIT=50  # failed attempts per client address for any user names
LOGIN_FAILURE_WINDOW_SECONDS=900
LOGIN_MAX_CONCURRENT=4  # process-wide authentication work limit, 1–64; saturation returns 429

# Request limits
WEBSOCKET_AUTH_TIMEOUT_SECONDS=10  # close a websocket connection that has not authenticated by then
DEPLOYMENT_CONTEXT_MAX_BYTES=65536  # largest JSON encoded context of POST /deployments/ (413 above)

# API configuration
API_URL=http://localhost:8000
```

`DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS` adds a safety window before unfinished deployments are considered orphaned by reconciliation on read endpoints and before starting a new deployment. It counts from the latest activity of the deployment (its start or the last reported step). Orphaned deployments are finished as failed with a `deployment orphaned` failure step that records the reason, see [docs/endpoints.md](docs/endpoints.md#orphaned-deployments). Increase the delay if step creation is delayed in your environment.

Deploy tasks stop their owned process group when the runtime budget expires and clean up
temporary config files before reporting failure. Each API report/finish response is
limited to 4096 wire bytes and 10 seconds per attempt. Task retry counts must be
1–8 and initial backoff 0–10 finite seconds (defaults 4/6 attempts, 3 seconds); see [runner limits](docs/deployment.md).

Only one deployment per service runs at a time: `POST /deployments/` returns `409 Conflict` (naming the running deployment id) while the service has an active deployment. See [docs/endpoints.md](docs/endpoints.md#post-deployments).

Service tokens are issued by configured administrators via `POST /service-token` or `python commands.py issueservicetoken --service S --user U --days N`, and can be revoked by those administrators via `DELETE /service-token/{jti}` or `python commands.py revokeservicetoken <jti>`. Tokens issued before revocation support (without `jti`) are rejected unless `LEGACY_SERVICE_TOKENS_ACCEPTED_UNTIL` is set; see the cutover steps in [docs/auth.md](docs/auth.md#service-token). Records of tokens expired or revoked more than `SERVICE_TOKEN_RETENTION_DAYS` days ago are deleted on token issue or with `python commands.py purgeservicetokens`. See [docs/auth.md](docs/auth.md#service-token).

Secret-bearing responses from `POST /token`, `POST /service-token`, `GET /services/` and
`GET /deployed-services/` carry `Cache-Control: private, no-store` and `Vary: Authorization`
(preserving CORS variation). Clients must fetch again with a valid credential instead of
retaining these responses in an HTTP cache. See [authentication docs](docs/auth.md).

Lifecycle settings are validated at startup (defaults are unchanged):

| Setting | Inclusive range |
| --- | --- |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`, `DEFAULT_EXPIRE_MINUTES` | 1–525600 minutes (one year) |
| `SERVICE_TOKEN_MAX_EXPIRE_DAYS`, `SERVICE_TOKEN_RETENTION_DAYS` | 1–3650 days (ten years) |
| `DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS` | 0–31536000 seconds (one year); zero disables the safety window |
| `WEBSOCKET_AUTH_TIMEOUT_SECONDS` | finite, greater than 0 and at most 86400 seconds (one day) |

Invalid or oversized values stop startup instead of overflowing date arithmetic or
silently disabling the websocket authentication deadline.

### Service Configuration

Services can use either relative or absolute paths for their deployment scripts:

```json
{
  "name": "myservice",
  "deploy_script": "deploy.sh"  // Relative path (default)
}

{
  "name": "myservice",
  "deploy_script": "/home/deploy/runners/myservice/deploy.py"  // Absolute path (supported)
}
```

When using absolute paths, ensure the `SUDO_USER` has appropriate permissions and sudoers rules are configured correctly.

`deploy_script` is the path of one executable, not a command line: fastDeploy runs
`sudo -u <SUDO_USER> <script> --config <file>` as an argument list without a shell, so the value is never
split into words and shell syntax in it has no effect.

## Development

### Running the development server

```shell
# Start all services (postgres, fastapi, frontend, docs)
just dev

# Or start individual services
just postgres      # PostgreSQL database
just fastapi       # FastAPI backend
just frontend      # Vue.js frontend
just docs-serve    # MkDocs documentation

# Or use honcho directly
honcho start
```

### Running tests

```shell
# Run all tests (Python + JavaScript)
just test

# Run specific test suites
just test-python           # Python tests only
just test-js              # JavaScript tests (using Vitest)
just coverage             # Run tests with coverage report

# Or run directly
uv run pytest             # Python tests
cd frontend && npm test   # Frontend tests (Vitest)
```

The Python tests use synthetic records and per-test temporary deployment configuration
files; they never require host `/var/tmp` access. They need the `deploy_test` PostgreSQL database (see above). They do not need a
frontend build: the test setup creates the empty, git-ignored `frontend/dist` directory the app
mounts, so a clean checkout can run `just test-python` directly.

The database defaults to `postgresql+asyncpg:///deploy_test` (local socket). To use another
database, set `DATABASE_URL` in the environment; the pytest configuration only provides the
default, for example:

```shell
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/deploy_test just test-python
```

Deployment history uses bounded pages: the UI shows the newest 50 deployments and
loads older pages with **Load more**. API consumers use `limit` (default 50, maximum
200), `before_id` and optional `service_id`; see [the paging contract](docs/endpoints.md#get-deployments).

### Continuous integration

`.github/workflows/ci.yml` runs on every branch push, on pull requests and on demand. It runs
`just lint`, `just typecheck` and `just test-python` against a `postgres:17` service container,
and in `frontend/` `npm ci`, `npm test` (Vitest) and `npm run build` (vue-tsc and Vite). The
workflow has read-only permissions, uses no secrets and does not deploy; deploys go through the
Ansible playbooks.

### Code quality

```shell
# Type checking
just typecheck            # or: uv run mypy deploy

# Linting and formatting (using the pinned ruff version via uvx)
just lint                 # Check code style
just lint-fix            # Fix code style issues

# Pre-commit hooks
just pre-commit-install  # Install git hooks
just pre-commit          # Run hooks on all files
```

## Documentation

This project uses [mkdocs.org](https://www.mkdocs.org) with [material theme](https://squidfunk.github.io/mkdocs-material/) for documentation.

### Building and serving documentation

```shell
# Serve documentation locally
just docs-serve           # Available at http://localhost:8001

# Build documentation
just docs-build          # Output in site/

# Update OpenAPI schema
just docs-openapi        # or: python commands.py docs --openapi
```

Layout:

    mkdocs.yml        # The configuration file
    docs/
        index.md      # The documentation home
        openapi.json  # Generated from FastAPI. Use with `!!swagger openapi.json!!`
        ...           # Other markdown pages, images and other files

## Project Structure

```
fastdeploy/
├── src/
│   └── deploy/         # Backend Python code (src layout)
│       ├── domain/     # Domain models and business logic
│       ├── adapters/   # Database and external adapters
│       ├── entrypoints/# FastAPI routes and endpoints
│       └── service_layer/# Services and message bus
├── frontend/           # Vue.js 3 frontend application
│   ├── src/           # Vue components and logic
│   └── tests/         # Frontend tests (Vitest)
├── tests/             # Python backend tests
│   ├── unit/          # Unit tests
│   ├── integration/   # Integration tests
│   └── e2e/           # End-to-end API tests
├── services/          # Service definitions and Ansible playbooks
├── docs/              # MkDocs documentation
└── ansible/           # Deployment playbooks
```

## Testing

### Backend (Python)
- Test framework: pytest with pytest-asyncio
- Run with: `just test-python` or `uv run pytest`
- Coverage: `just coverage`

### Frontend (TypeScript/Vue)
- Test framework: Vitest (migrated from Jest)
- Run with: `just test-js` or `cd frontend && npm test`
- Interactive UI: `cd frontend && npm run test:ui`

## Available Commands

The project uses `just` for task automation. Run `just --list` to see all available commands.

Common commands:
- `just dev` - Start all development services
- `just test` - Run all tests
- `just lint` - Check code style
- `just typecheck` - Run type checking
- `just status` - Check service status
- `just cleanup` - Kill leftover processes

For help: `just help`

## Technologies

- **Backend**: FastAPI with async PostgreSQL (asyncpg/SQLAlchemy)
- **Frontend**: Vue.js 3 with Vite and TypeScript
- **Testing**: pytest (Python), Vitest (JavaScript/TypeScript)
- **Documentation**: MkDocs with Material theme
- **Code Quality**: ruff (linting/formatting), mypy (type checking), pre-commit hooks
- **Deployment**: Ansible playbooks for Linux hosts
- **Real-time**: WebSockets for deployment monitoring
