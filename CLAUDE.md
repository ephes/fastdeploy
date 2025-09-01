# CLAUDE.md - AI Assistant Instructions for fastDeploy

## Project Overview

fastDeploy is a deployment automation platform that enables both technical and non-technical users to deploy web applications via API or web interface. It provides real-time deployment monitoring through WebSockets and manages infrastructure using Ansible playbooks.

### Architecture
- **Backend**: FastAPI with async PostgreSQL (asyncpg/SQLAlchemy)
- **Frontend**: Vue.js 3 with Vite
- **Documentation**: MkDocs with Material theme
- **Testing**: pytest (Python), Vitest (TypeScript/Vue)
- **Process Management**: Currently migrating from Honcho to justfile
- **Infrastructure**: Ansible playbooks for Linux host deployments

## Development Workflow

### Setup
1. **Python**: Project requires Python 3.10+ (fully compatible with Python 3.13)
2. **Database**: PostgreSQL with separate test database
3. **Virtual Environment**: Using `uv` for package management
4. **Frontend**: Node.js with npm for Vue.js development

### Running Tests
```bash
# Run all tests (Python + JS)
uv run pytest  # Python tests
cd frontend && npm test  # Frontend tests

# Or use the command tool (being migrated to justfile)
uv run python commands.py test
```

### Starting Development Server
```bash
# Using honcho (current, being migrated)
honcho start

# Individual services
postgres -D databases/postgres
uvicorn deploy.entrypoints.fastapi_app:app --reload
cd frontend && npm run dev
mkdocs serve
```

## Code Style and Conventions

### Python Code Style
- **Formatter/Linter**: Using `ruff` for both linting and formatting
- **Line Length**: 119 characters
- **Import Order**: Managed by ruff (future, stdlib, third-party, first-party, local)
- **Type Hints**: Use type hints for all new code
- **Async/Await**: Use async patterns throughout (FastAPI, SQLAlchemy, asyncpg)

### Pre-commit Hooks
The project uses pre-commit hooks configured in `.pre-commit-config.yaml`:
- ruff (linting and formatting)
- mypy (type checking)
- Standard hooks (trailing whitespace, YAML/JSON/TOML validation)

Run `pre-commit install` to set up hooks locally.

### Testing Guidelines
- **Fixtures**: Use pytest-asyncio fixtures with explicit `loop_scope`
- **Database Tests**: Use rollback fixtures to ensure test isolation
- **Async Tests**: Mark with `@pytest.mark.asyncio`
- **Test Organization**:
  - `tests/unit/` - Unit tests
  - `tests/integration/` - Integration tests
  - `tests/e2e/` - End-to-end API tests
  - `frontend/tests/` - Frontend TypeScript tests

## Common Tasks

### Adding a New Service
Services are defined in the `services/` directory. Each service includes:
- Ansible playbooks for deployment
- Configuration files
- Service-specific documentation

### Database Migrations
Currently manual - use SQLAlchemy models in `deploy/adapters/orm.py`

### API Development
- Routers in `deploy/entrypoints/routers/`
- Domain models in `deploy/domain/model.py`
- Use Pydantic v2 patterns (ConfigDict, model_dump, etc.)

## Important Patterns

### Dependency Injection
FastAPI's dependency injection is used extensively:
- Database sessions via Unit of Work pattern
- Authentication via OAuth2 dependencies
- Message bus for command/event handling

### Event-Driven Architecture
- Commands in `deploy/domain/commands.py`
- Events in `deploy/domain/events.py`
- Handlers in `deploy/service_layer/handlers.py`
- Message bus in `deploy/service_layer/messagebus.py`

### WebSocket Communication
Real-time updates during deployments via WebSocket connections:
- Connection manager in `deploy/adapters/websocket.py`
- Authentication required for WebSocket connections

## Security Considerations

### Authentication
- JWT tokens for API authentication
- Service tokens for inter-service communication
- Deployment tokens for deployment operations

### SSH Key Management
- fastDeploy manages root SSH keys for target systems
- Never expose or log SSH keys
- Use secure storage for credentials

### API Security
- All endpoints require authentication except health checks
- Use OAuth2 password flow for user authentication
- Service accounts for automated deployments

## Deployment Process

### Target Environments
- **Staging**: Test deployments before production
- **Production**: Live customer deployments

### Deployment Flow
1. User initiates deployment via API or web UI
2. fastDeploy creates deployment record
3. Ansible playbooks execute on target host
4. Real-time status updates via WebSocket
5. Deployment marked complete/failed

## Troubleshooting

### Common Issues
1. **Test Failures**: Check PostgreSQL test database is running
2. **Import Errors**: Ensure virtual environment is activated
3. **WebSocket Issues**: Check authentication tokens
4. **Deployment Failures**: Review Ansible playbook output

### Debugging Tools
- `ipdb` for Python debugging
- Vue DevTools for frontend
- PostgreSQL query logging
- FastAPI automatic API documentation at `/docs`

## Migration Notes

### In Progress
1. **Justfile Migration**: Replacing `commands.py` with justfile for better task management
2. **Frontend Test Migration**: Moving from Jest to Vitest
3. **Process Management**: Moving from Honcho to justfile-based process management

### Completed
1. **Python 3.13 Support**: Full compatibility achieved
2. **Ruff Migration**: Replaced black, isort, flake8 with ruff
3. **Pydantic v2**: Updated all models and configurations
4. **httpx 0.28+**: Updated test suite for latest httpx
5. **pytest-asyncio 1.1+**: Updated fixtures for latest version

## Best Practices

### When Writing Code
1. Follow existing patterns in the codebase
2. Add type hints to all new functions
3. Write tests for new functionality
4. Update documentation for API changes
5. Use async/await consistently
6. Handle errors gracefully with proper logging

### When Reviewing Code
1. Check for security implications
2. Ensure tests are included
3. Verify async patterns are used correctly
4. Check for proper error handling
5. Ensure code follows project conventions

### Git Workflow
1. Create feature branches from main
2. Write descriptive commit messages
3. Include issue numbers in commits when applicable
4. Ensure all tests pass before committing
5. Run pre-commit hooks before pushing

## Future Improvements

See `todo.md` for the current list of planned improvements and technical debt items.

## Contact

For questions about the deployment infrastructure or architecture decisions, consult the project maintainer.