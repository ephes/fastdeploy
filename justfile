# Justfile for fastDeploy project development

# Default recipe - show available commands
default:
    @just --list

# === Environment Setup ===

# Create virtual environment and install dependencies
install:
    @echo "Creating virtual environment and installing dependencies..."
    uv venv -p python3.12
    uv sync
    @echo "✓ Dependencies installed"
    @echo "Activate with: source .venv/bin/activate"

# Update dependencies
update:
    @echo "Updating Python dependencies..."
    uv lock --upgrade
    uv sync
    @echo "Updating frontend dependencies..."
    cd frontend && npm update
    @echo "✓ All dependencies updated"

# === Database Management ===

# Initialize PostgreSQL database
db-init:
    @echo "Initializing PostgreSQL database..."
    initdb databases/postgres
    @echo "✓ Database initialized"
    @echo "Start with: just db-start"

# Start PostgreSQL database
db-start:
    @echo "Starting PostgreSQL..."
    postgres -D databases/postgres

# Create development databases
db-create:
    @echo "Creating development databases..."
    createdb deploy || echo "Database 'deploy' already exists"
    createuser deploy || echo "User 'deploy' already exists"
    createdb deploy_test || echo "Database 'deploy_test' already exists"
    @echo "Copying schema to test database..."
    pg_dump deploy | psql deploy_test
    @echo "✓ Databases created"

# Create initial user (interactive or via environment variables)
createuser:
    @echo "Creating user..."
    uv run python commands.py createuser

# Sync services from filesystem to database
syncservices:
    @echo "Syncing services..."
    uv run python commands.py syncservices

# === Development Server ===

# Check if services are already running
check-ports:
    @echo "Checking for running services..."
    @if lsof -i :8000 > /dev/null 2>&1; then \
        echo "❌ Port 8000 already in use (FastAPI)"; \
        echo "   PID: $(lsof -ti :8000)"; \
        exit 1; \
    fi
    @if lsof -i :5432 > /dev/null 2>&1; then \
        echo "⚠️  Port 5432 already in use (PostgreSQL)"; \
        echo "   This might be your system PostgreSQL - checking..."; \
        if pgrep -f "postgres -D databases/postgres" > /dev/null; then \
            echo "   ❌ Local dev PostgreSQL already running"; \
            echo "   PID: $(pgrep -f 'postgres -D databases/postgres')"; \
            exit 1; \
        else \
            echo "   ✓ System PostgreSQL detected, will use it"; \
        fi; \
    fi
    @if lsof -i :5173 > /dev/null 2>&1; then \
        echo "❌ Port 5173 already in use (Vite)"; \
        echo "   PID: $(lsof -ti :5173)"; \
        exit 1; \
    fi
    @if lsof -i :8001 > /dev/null 2>&1; then \
        echo "❌ Port 8001 already in use (MkDocs)"; \
        echo "   PID: $(lsof -ti :8001)"; \
        exit 1; \
    fi
    @echo "✓ All ports available"

# Kill any leftover processes from previous runs
cleanup:
    @echo "Cleaning up any leftover processes..."
    @-pkill -f "postgres -D databases/postgres" 2>/dev/null || true
    @-pkill -f "uvicorn deploy.entrypoints.fastapi_app:app" 2>/dev/null || true
    @-pkill -f "mkdocs serve" 2>/dev/null || true
    @-pkill -f "npm run dev" 2>/dev/null || true
    @echo "✓ Cleanup complete"

# Start development server (all services)
dev: check-ports
    @echo "Starting all development services..."
    @echo "This will start: postgres, fastapi, frontend, and docs"
    @echo "Press Ctrl+C to stop all services"
    honcho start

# Start development server (backend only: postgres + fastapi)
dev-backend: check-ports
    @echo "Starting backend services (postgres + fastapi)..."
    honcho start postgres uvicorn

# Start individual services
postgres:
    @echo "Starting PostgreSQL..."
    postgres -D databases/postgres

fastapi:
    @echo "Starting FastAPI server..."
    PYTHONPATH=src PYTHONUNBUFFERED=true uvicorn deploy.entrypoints.fastapi_app:app --reload --host 0.0.0.0 --port 8000

frontend:
    @echo "Starting Vue.js frontend..."
    cd frontend && npm run dev

docs-serve:
    @echo "Starting documentation server..."
    mkdocs serve -a 127.0.0.1:8001

# === Testing ===

# Run all tests (Python + JavaScript)
test:
    @echo "Running Python tests..."
    SECRET_KEY="${SECRET_KEY:-test-secret-key}" PATH_FOR_DEPLOY="${PATH_FOR_DEPLOY:-/tmp/deploy}" PYTHONPATH=src uv run pytest
    @echo "Running JavaScript tests..."
    cd frontend && npm test

# Run Python tests only
test-python *ARGS:
    SECRET_KEY="${SECRET_KEY:-test-secret-key}" PATH_FOR_DEPLOY="${PATH_FOR_DEPLOY:-/tmp/deploy}" PYTHONPATH=src uv run pytest {{ARGS}}

# Run JavaScript tests only
test-js:
    cd frontend && npm test

# Run tests with coverage
coverage:
    @echo "Running tests with coverage..."
    SECRET_KEY="${SECRET_KEY:-test-secret-key}" PATH_FOR_DEPLOY="${PATH_FOR_DEPLOY:-/tmp/deploy}" PYTHONPATH=src uv run coverage run -m pytest
    PYTHONPATH=src uv run coverage html
    @echo "Coverage report generated in htmlcov/"
    @echo "Opening coverage report..."
    open htmlcov/index.html || xdg-open htmlcov/index.html 2>/dev/null || echo "Please open htmlcov/index.html manually"

# Run type checking
typecheck:
    @echo "Running mypy type checker..."
    PYTHONPATH=src uv run mypy src/deploy

# Run linting
lint:
    @echo "Running ruff linter..."
    uv run ruff check src/deploy tests
    @echo "Running ruff formatter..."
    uv run ruff format --check src/deploy tests

# Fix linting issues
lint-fix:
    @echo "Fixing linting issues..."
    uv run ruff check --fix src/deploy tests
    uv run ruff format src/deploy tests

# === Documentation ===

# Build documentation
docs-build:
    @echo "Building documentation..."
    @if [ ! -f docs/openapi.json ]; then \
        echo "Generating OpenAPI schema..."; \
        just docs-openapi; \
    fi
    mkdocs build
    @echo "✓ Documentation built in site/"

# Generate OpenAPI schema
docs-openapi:
    @echo "Generating OpenAPI schema..."
    uv run python commands.py docs --openapi
    @echo "✓ OpenAPI schema generated"

# Clean documentation build
docs-clean:
    @echo "Cleaning documentation build..."
    rm -rf site/
    @echo "✓ Documentation cleaned"

# === Jupyter ===

# Start Jupyter notebook
notebook:
    @echo "Starting Jupyter notebook..."
    PYTHONPATH=$(pwd)/src uv run jupyter notebook --notebook-dir notebooks

# Start JupyterLab
jupyterlab:
    @echo "Starting JupyterLab..."
    PYTHONPATH=$(pwd)/src uv run jupyter-lab

# === Deployment ===

# Deploy to staging environment
deploy-staging:
    @echo "Deploying to staging..."
    cd ansible && ansible-playbook deploy.yml --limit staging

# Deploy to production environment
deploy-production:
    @echo "⚠️  WARNING: Deploying to PRODUCTION!"
    @echo "Press Enter to continue or Ctrl+C to cancel..."
    @read _
    cd ansible && ansible-playbook deploy.yml --limit production

# === Utilities ===

# Run pre-commit hooks on all files
pre-commit:
    @echo "Running pre-commit hooks..."
    uv run pre-commit run --all-files

# Install pre-commit hooks
pre-commit-install:
    @echo "Installing pre-commit hooks..."
    uv run pre-commit install
    @echo "✓ Pre-commit hooks installed"

# Show current Python version
python-version:
    @echo "Python version:"
    @uv run python --version

# Show project status
status:
    @echo "=== Project Status ==="
    @echo "Python version: $(uv run python --version)"
    @echo "Node version: $(node --version)"
    @echo "npm version: $(npm --version)"
    @echo ""
    @echo "=== Service Ports ==="
    @echo -n "PostgreSQL (5432): "
    @lsof -i :5432 > /dev/null 2>&1 && echo "✓ Running" || echo "✗ Not running"
    @echo -n "FastAPI (8000): "
    @lsof -i :8000 > /dev/null 2>&1 && echo "✓ Running" || echo "✗ Not running"
    @echo -n "Frontend (5173): "
    @lsof -i :5173 > /dev/null 2>&1 && echo "✓ Running" || echo "✗ Not running"
    @echo -n "Docs (8001): "
    @lsof -i :8001 > /dev/null 2>&1 && echo "✓ Running" || echo "✗ Not running"

# === Help ===

# Show help for common issues
help:
    @echo "=== fastDeploy Development Help ==="
    @echo ""
    @echo "Quick Start:"
    @echo "  just install        # Install dependencies"
    @echo "  just db-init        # Initialize database (first time only)"
    @echo "  just db-create      # Create databases"
    @echo "  just dev            # Start all services"
    @echo ""
    @echo "Common Tasks:"
    @echo "  just test           # Run all tests"
    @echo "  just lint           # Check code style"
    @echo "  just lint-fix       # Fix code style issues"
    @echo "  just coverage       # Run tests with coverage"
    @echo ""
    @echo "Troubleshooting:"
    @echo "  just status         # Check service status"
    @echo "  just cleanup        # Kill leftover processes"
    @echo "  just check-ports    # Check if ports are in use"
    @echo ""
    @echo "For more commands: just --list"
