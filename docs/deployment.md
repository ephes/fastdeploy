# FastDeploy Deployment Guide

This document explains how FastDeploy itself is deployed and how services are registered with it.

## FastDeploy Self-Deployment

FastDeploy is deployed using the ops-control infrastructure automation system with the `fastdeploy_deploy` role from ops-library.

### Deployment Methods

FastDeploy supports two deployment methods:

#### Development Deployment (rsync)
Uses local working directory for rapid development:

```bash
# Deploy from local development directory
just deploy-one fastdeploy
```

This method:
- Syncs code from `/Users/jochen/projects/fastdeploy` via rsync
- Ideal for testing changes before committing
- Preserves file permissions and symlinks
- Allows rapid iteration without git commits

#### Production Deployment (git)
Uses git repository for production deployment:

```bash
# Register FastDeploy for self-deployment
just register-one fastdeploy-self

# Then deploy via FastDeploy web UI
```

This method:
- Clones from GitHub repository
- Ensures reproducible deployments
- Supports tagged releases
- Used for production environments

### Deployment Process

The `fastdeploy_deploy` role handles:

1. **Database Setup**
   - PostgreSQL database creation
   - Database migrations
   - Initial user creation

2. **Python Environment**
   - Virtual environment creation with uv
   - Dependency installation from `uv.lock`

3. **Frontend Build**
   - Node.js/npm dependency installation
   - Production build with Vite
   - Static file serving configuration

4. **Service Configuration**
   - Systemd service setup
   - Environment file creation
   - Log rotation configuration

5. **Initialization**
   - Admin user creation
   - Service synchronization from filesystem

### Configuration

Key configuration variables:

```yaml
# Database
fastdeploy_postgres_host: localhost
fastdeploy_postgres_database: fastdeploy
fastdeploy_postgres_user: fastdeploy

# FastDeploy settings
fastdeploy_site_path: /home/fastdeploy/site
fastdeploy_user: fastdeploy
fastdeploy_service_name: fastdeploy

# Deployment method
fastdeploy_deploy_method: rsync  # or git
fastdeploy_source_path: /Users/jochen/projects/fastdeploy  # for rsync
fastdeploy_git_repo: https://github.com/ephes/fastdeploy.git  # for git
```

## Service Registration

Services are registered with FastDeploy using the `fastdeploy_register_service` role.

### Registration Process

1. **Create Registration Playbook**

Create `playbooks/register-<service>.yml` in ops-control:

```yaml
---
- name: Register service with FastDeploy
  hosts: macmini
  become: true
  tasks:
    - name: Register service
      include_role:
        name: local.ops_library.fastdeploy_register_service
      vars:
        fd_service_name: "myservice"
        fd_service_description: "My service description"
        fd_fastdeploy_root: "/home/fastdeploy/site"
        fd_runner_content: |
          #!/usr/bin/env python3
          # Custom deployment script here
```

2. **Register the Service**

```bash
just register-one myservice
```

### Registration Components

The registration process creates:

#### Service Directory Structure
```
/home/fastdeploy/site/services/myservice/
├── config.json          # Service metadata for FastDeploy UI
└── deploy.py            # Deployment script (FastDeploy calls this)

/home/deploy/runners/myservice/
└── deploy.py            # Source deployment script
```

#### Security Configuration
- Deploy user creation with restricted permissions
- Sudoers rules for cross-user execution (`fastdeploy` → `deploy`)
- SOPS age keys for secrets decryption
- Proper file permissions and ownership

#### Service Configuration
The `config.json` contains:

```json
{
  "name": "myservice",
  "description": "Service description",
  "deploy_script": "deploy.py",
  "steps": [
    {"name": "prepare"},
    {"name": "bootstrap"},
    {"name": "ansible"},
    {"name": "verify"}
  ]
}
```

### Deployment Script Requirements

Registered services must provide a deployment script that:

1. **Accepts Configuration**
   ```python
   parser = argparse.ArgumentParser()
   parser.add_argument('--config', help='Configuration file path')
   args = parser.parse_args()
   ```

2. **Handles FastDeploy Config Structure**
   ```python
   config = json.load(open(args.config))
   deployment_id = config.get('deployment_id')
   service_name = config.get('deploy_script', '').split('/')[0]
   ```

3. **Outputs JSON Status**
   ```python
   def emit_step(name, state, message=""):
       step_data = {"name": name, "state": state}
       if message:
           step_data["message"] = message
       print(json.dumps(step_data), flush=True)

   # States: "running", "success", "failure"
   emit_step("Install packages", "running", "Installing dependencies...")
   emit_step("Install packages", "success", "All packages installed")
   ```

4. **Returns Exit Code**
   - Return `0` for success
   - Return non-zero for failure
   - Handle exceptions gracefully

## Security Model

FastDeploy uses a multi-user security model:

```
Web Request → FastDeploy (fastdeploy user)
    ↓
    Creates secure config in /var/tmp/
    ↓
    sudo → deploy.py (deploy user)
    ↓
    - Clones ops-control
    - Runs ansible-playbook
    - Has access to SOPS keys
```

Key security features:
- **User isolation**: FastDeploy runs as `fastdeploy`, deployments as `deploy`
- **Sudo restrictions**: Specific sudoers rules per service
- **Config security**: Temporary config files with 0o640 permissions
- **Secrets management**: SOPS-encrypted secrets, keys only readable by deploy user
- **No network privileges**: Deploy user cannot make outbound connections

## Troubleshooting

### Common Issues

1. **Service not appearing in UI**
   - Check `config.json` exists in `/home/fastdeploy/site/services/`
   - Run `python commands.py syncservices` to refresh
   - Verify API token is valid

2. **Deployment fails with permission denied**
   - Check sudoers rule exists in `/etc/sudoers.d/fastdeploy_<service>`
   - Verify deploy user exists and has correct permissions
   - Check config file permissions (should be 0o640)

3. **"deployments succeed but no steps execute"**
   - Often caused by systemd hardening features
   - Check `NoNewPrivileges=false` and `PrivateTmp=false` in service
   - See [systemd-hardening.md](systemd-hardening.md) for details

4. **Script errors with 'service_name' KeyError**
   - Extract service name from `deploy_script` field, not `service_name`
   - Use: `service_name = config.get('deploy_script', '').split('/')[0]`

### Debugging Steps

1. Check FastDeploy logs: `journalctl -u fastdeploy -f`
2. Test deployment script manually:
   ```bash
   sudo -u deploy /home/deploy/runners/<service>/deploy.py --config /path/to/config.json
   ```
3. Verify database state: Check deployments and steps tables
4. Test service registration: `python commands.py syncservices`

## Development Workflow

1. **Test locally**: Use `just deploy-one fastdeploy` for development
2. **Register service**: Create registration playbook and run `just register-one <service>`
3. **Test deployment**: Use FastDeploy web UI or test script
4. **Iterate**: Make changes and re-deploy as needed
5. **Production**: Register FastDeploy for self-deployment when ready

This workflow allows rapid development while maintaining production deployment capabilities.
