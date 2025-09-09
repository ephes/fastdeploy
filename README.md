# fastDeploy

A deployment automation platform that enables both technical and non-technical users to deploy web applications via API or web interface. Features real-time deployment monitoring through WebSockets and manages infrastructure using Ansible playbooks.

## Requirements

- Python 3.10+ (fully compatible with Python 3.13)
- PostgreSQL
- Node.js and npm (for frontend development)
- uv (for Python package management)

## Quick Start

```shell
# Install dependencies
just install

# Initialize and setup database
just db-init        # First time only
just db-start       # In a separate terminal
just db-create      # Create deploy and deploy_test databases
just createuser     # Create initial user

# Start all development services
just dev            # Starts postgres, fastapi, frontend, and docs

# Note: The project uses a src layout for Python code.
# The backend package 'deploy' is located at src/deploy/
```

## Installation for development

### Create a venv & activate it and install the dev requirements
```shell
uv venv -p python3.13  # or python3.12, python3.11, python3.10
source .venv/bin/activate  # or .venv/bin/activate.fish for fish shell
uv sync
```

### Set up the database

#### Using justfile (recommended):
```shell
just db-init        # Initialize PostgreSQL database
just db-start       # Start PostgreSQL (in a different terminal)
just db-create      # Create deploy and deploy_test databases
just createuser     # Create initial user and tables
just syncservices   # Sync services from filesystem to database
```

#### Or manually:
```shell
initdb databases/postgres
postgres -D databases/postgres  # in a different terminal tab
createdb deploy
createuser deploy
python commands.py createuser  # will also create the tables

# Create a test database and copy the schema over
createdb deploy_test
pg_dump deploy | psql deploy_test
```

## Configuration

### Environment Variables

fastDeploy uses environment variables for configuration. Create a `.env` file in the project root:

```shell
# Required
SECRET_KEY=your-secret-key-here
PATH_FOR_DEPLOY=/path/to/deploy
DATABASE_URL=postgresql+asyncpg:///deploy

# Deployment configuration
SUDO_USER=deploy  # User to run deployment scripts as (default: jochen)

# API configuration  
API_URL=http://localhost:8000
```

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

### Code quality

```shell
# Type checking
just typecheck            # or: uv run mypy deploy

# Linting and formatting (using ruff)
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
