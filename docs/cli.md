# Command Line Interface

The project uses `just` for task automation, providing a comprehensive set of commands for development, testing, and deployment. The legacy `commands.py` is still available but `just` is now the recommended approach.

# Usage

```shell
# Show all available commands
just --list

# Get help
just help
```

## Quick Start Commands

```shell
just install        # Install dependencies
just db-init        # Initialize database (first time only)
just db-create      # Create databases
just dev            # Start all services
```

## Development Commands

### Environment Setup
- `just install` - Create virtual environment and install dependencies
- `just update` - Update all dependencies (Python and JavaScript)

### Database Management
- `just db-init` - Initialize PostgreSQL database
- `just db-start` - Start PostgreSQL database
- `just db-create` - Create development and test databases
- `just createuser` - Create initial user (interactive or via environment variables)
- `just syncservices` - Sync services from filesystem to database

### Development Server
- `just dev` - Start all services (postgres, fastapi, frontend, docs)
- `just dev-backend` - Start backend only (postgres + fastapi)
- `just postgres` - Start PostgreSQL only
- `just fastapi` - Start FastAPI server only
- `just frontend` - Start Vue.js frontend only
- `just docs-serve` - Start documentation server only

### Testing
- `just test` - Run all tests (Python + JavaScript)
- `just test-python [ARGS]` - Run Python tests with optional arguments
- `just test-js` - Run JavaScript tests (using Vitest)
- `just coverage` - Run tests with coverage report
- `just typecheck` - Run mypy type checker

### Code Quality
- `just lint` - Check code style with ruff (pinned version run via `uvx`, matching pre-commit)
- `just lint-fix` - Fix code style issues
- `just pre-commit` - Run pre-commit hooks on all files
- `just pre-commit-install` - Install pre-commit hooks

### Documentation
- `just docs-build` - Build documentation
- `just docs-openapi` - Generate OpenAPI schema
- `just docs-clean` - Clean documentation build

### Deployment
- `just deploy-staging` - Deploy to staging environment
- `just deploy-production` - Deploy to production (with confirmation)

### Utilities
- `just status` - Show project and service status
- `just check-ports` - Check if required ports are available
- `just cleanup` - Kill leftover processes
- `just python-version` - Show current Python version
- `just notebook` - Start Jupyter notebook
- `just jupyterlab` - Start JupyterLab

## Legacy commands.py

The original `commands.py` is still available for compatibility:

```shell
python commands.py [COMMAND] [OPTIONS]
```

Available commands include createuser, syncservices, test, docs, and others. Run `python commands.py --help` for the full list.

# Commands In Detail

## syncservices

This command syncs the services from the filesystem with the services in the
database. If a service is in the filesystem but not in the database, it will be
added to the database and if it's in the database but not in the filesystem, it
will be removed together with all of its deployments and steps.

To protect the deployment history, the command refuses to delete anything and
exits with status 1 when the services directory is empty while the database has
services, or when more than half of the services would be deleted. Check the
services directory first; if the deletion is intended, rerun with `--force`.
Services with a running deployment are never deleted (not even with `--force`);
they are reported as skipped and removed by a later sync.

The command prints the updated (or added), deleted and skipped services.

```shell
# Using just (recommended)
just syncservices

# Or using commands.py
python commands.py syncservices
python commands.py syncservices --force  # allow deleting all or most services
```

## issueservicetoken

Issues a recorded, revocable service token and prints it once. `--service` and
`--user` must exist, `--days` must be between 1 and `SERVICE_TOKEN_MAX_EXPIRE_DAYS`
(default 90), and `--origin` (default `cli`) is recorded with the token. Only the
token is written to stdout, so a script can capture it; the token id (`jti`) and
expiry go to stderr. If the token cannot be issued, the reason goes to stderr and
the command exits with status 1. Run it with the deployed `.env` (on a host:
`cd /home/fastdeploy/site && sudo -u fastdeploy .venv/bin/python commands.py ...`).

```shell
python commands.py issueservicetoken --service echoport --user admin --days 90 --origin ops-control
```

The token cannot be shown again; issue a new one (and revoke the old one) if it
is lost.

## listservicetokens / revokeservicetoken

`listservicetokens` lists the issued service tokens with their id (`jti`),
service, user, origin, expiry and revocation state. `revokeservicetoken <jti>`
revokes a service token, so deployments can no longer be started with it. It
exits with status 1 if no token with this id was issued.

```shell
python commands.py listservicetokens
python commands.py revokeservicetoken <jti>
```

## purgeservicetokens

Deletes the records of service tokens that expired or were revoked more than
`--older-than-days` days ago (default: `SERVICE_TOKEN_RETENTION_DAYS`, 30).
Such tokens are rejected anyway. The same cleanup also runs whenever a new
service token is issued.

```shell
python commands.py purgeservicetokens
python commands.py purgeservicetokens --older-than-days 7
```

## createuser

Creates a new user in the system. Username and password can be set via environment variables (useful for automation with Ansible) or interactively via the command line.

```shell
# Using just (recommended)
just createuser

# Or using commands.py
python commands.py createuser
```

## Running Tests

The project uses pytest for Python tests and Vitest for JavaScript/TypeScript tests.

```shell
# Run all tests
just test

# Run Python tests only
just test-python
just test-python tests/unit  # Run specific test directory

# Run JavaScript tests only
just test-js

# Run with coverage
just coverage
```
