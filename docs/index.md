# Welcome to fastDeploy

fastDeploy is a privileged deployment automation platform that serves as a secure API-driven interface for infrastructure automation. It acts as a security boundary between unprivileged client applications and privileged system operations, enabling safe execution of infrastructure changes without granting direct root access to client systems.

## Core Purpose

fastDeploy provides controlled, auditable execution of privileged operations including:
- Deploying web applications, mail servers, and databases
- Managing system packages and updates
- Performing backup and restore operations
- Compiling software from source
- Running any automation script that produces JSON progress output

## Key Features

- **Security Boundary**: Deployment processes run as separate user with access to secrets that fastDeploy cannot read
- **Multi-layered Security**: Even if compromised, fastDeploy can only run pre-registered scripts, not access secrets
- **Real-time Monitoring**: WebSocket-based live deployment status updates
- **API-first Design**: Complete REST API for programmatic operations
- **Token-based Authentication**: Four token types for different authorization scopes
- **Service Discovery**: Deployed services can query for other deployed services
- **Process Isolation**: Each deployment runs in separate process with different privileges

## Quick Start

### Prerequisites

- Python 3.10+ (fully compatible with Python 3.13)
- PostgreSQL
- Node.js and npm (for frontend development)
- uv (for Python package management)

### Installation

```shell
# Install dependencies
just install

# Setup database
just db-init
just db-start
just db-create
just createuser

# Start development server
just dev
```

## Architecture

- **Backend**: FastAPI with async PostgreSQL (asyncpg/SQLAlchemy)
- **Frontend**: Vue.js 3 with Vite and TypeScript
- **Testing**: pytest (Python), Vitest (JavaScript/TypeScript)
- **Deployment**: Ansible playbooks for Linux hosts

## API Documentation

The complete API documentation is available below:

!!swagger openapi.json!!
