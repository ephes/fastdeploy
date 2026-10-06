Unreleased
==========

### Features
- Single-flight deployments per service: `POST /deployments/` returns `409 Conflict` with the running
  deployment id while the service already has an active deployment, instead of spawning a second
  concurrent deploy. Check and insert are serialized by a database row lock on the service, orphaned
  deployments of the service do not block (they are finished as part of a successful start), and deployments older than the deployment token
  lifetime no longer block. Addresses the per-service limit from security review #07.

### Security
- Websocket authentication hardening (`/deployments/ws/{client_id}`): any failed authentication
  (including a valid service, deployment or config token, or a token for a deleted user) now sends
  an authentication failure and closes the connection (code `1008`) instead of leaving it
  registered. Connection cleanup runs on every exit path, so rejected or server-closed sockets no
  longer accumulate in memory.
- A client id that is still connected can no longer be taken over: a second connection with the
  same id is refused, the id is bound to the authenticated user for the connection's lifetime
  (re-authenticating as another user closes the connection), and the "client left" broadcast no
  longer includes the client id. Only authenticated connections receive or trigger broadcasts.
- Each connection has at most one session expiry timer; re-authentication replaces it and
  disconnecting cancels it, so stale timers no longer close re-authenticated sessions or a newer
  connection reusing the id.

### Development
- The Python test suite runs on a clean checkout without a frontend build: the test setup creates
  the git-ignored `frontend/dist` directory that the app mounts at import time.

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
