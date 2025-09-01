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
- `just lint` - Check code style with ruff
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
will be removed.

This command does not take any arguments.

```shell
# Using just (recommended)
just syncservices

# Or using commands.py
python commands.py syncservices
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
