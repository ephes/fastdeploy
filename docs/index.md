# Welcome to FastDeploy

FastDeploy is a deployment automation platform that enables both technical and non-technical users to deploy web applications via API or web interface. It provides real-time deployment monitoring through WebSockets and manages infrastructure using Ansible playbooks.

## Features

- **Multi-tenant Architecture**: Secure isolation between different deployments
- **Real-time Monitoring**: WebSocket-based live deployment status updates
- **API-first Design**: Complete REST API for programmatic deployments
- **Web Interface**: User-friendly interface for non-technical users
- **Infrastructure as Code**: Ansible playbooks for reproducible deployments
- **Service Management**: Flexible service definitions and configurations

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
