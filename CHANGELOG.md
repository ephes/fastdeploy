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
