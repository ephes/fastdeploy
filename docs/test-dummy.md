# Test Dummy Service

The test_dummy service is a complete example service that demonstrates FastDeploy service registration and deployment patterns. It serves as both a testing tool and a template for building other services.

## Overview

The test_dummy service provides:
- **Working example** of FastDeploy service registration
- **Template code** for building deployment scripts
- **Testing capabilities** for FastDeploy functionality
- **Documentation** through working implementation

## Features

✅ **Real-time Progress Tracking**: JSON status output for FastDeploy UI
✅ **Proper Configuration Handling**: Parses FastDeploy's config structure
✅ **Realistic Deployment Simulation**: Multiple steps with timing
✅ **Error Handling**: Graceful handling of exceptions
✅ **From-scratch Compatible**: Works when redeploying entire infrastructure
✅ **Unified Commands**: Integrates with `just register-one` pattern

## Registration

The test_dummy service is registered using the `fastdeploy_register_service` role:

```bash
# Register the service with FastDeploy
just register-one test-dummy
```

This creates:
- Service configuration in FastDeploy UI
- Deployment script with proper security isolation
- Sudoers rules for cross-user execution
- Service metadata in `/home/fastdeploy/site/services/test_dummy/`

## Deployment Script

The test_dummy deployment script demonstrates all required FastDeploy patterns:

### Configuration Handling

```python
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='Path to configuration file')
    args = parser.parse_args()

    # Read configuration if provided
    config = {}
    if args.config and Path(args.config).exists():
        config = read_config_file(args.config)

    # Extract service name from deploy_script path
    deploy_script = config.get('deploy_script', '')
    service_name = deploy_script.split('/')[0] if '/' in deploy_script else 'test_dummy'
```

### JSON Status Output

```python
def emit_step(name, state, message=""):
    """Emit a step status update."""
    step_data = {"name": name, "state": state}
    if message:
        step_data["message"] = message
    print(json.dumps(step_data), flush=True)

# Usage
emit_step("Initialize deployment", "success", f"Starting deployment for {service_name}")
emit_step("Install dependencies", "running", "Installing dependencies...")
emit_step("Install dependencies", "success", "All packages installed")
```

### Deployment Steps

The script simulates a realistic deployment with these steps:

1. **Validate deployment environment**
2. **Clone/update git repository**
3. **Install dependencies**
4. **Configure service**
5. **Setup systemd service**
6. **Start/restart service**
7. **Run health check**
8. **Clean up old versions**
9. **Deployment complete**

Each step shows both "running" and "success" states for realistic progress tracking.

### Error Handling

```python
try:
    for step in steps:
        emit_step(step, "running", f"Executing: {step}")
        time.sleep(2)  # Simulate work
        emit_step(step, "success", f"Completed: {step}")

    return 0

except Exception as e:
    emit_step("Deployment error", "failure", f"Unexpected error: {e}")
    return 1
```

## Testing

### Manual Testing

Test the deployment using the FastDeploy test script:

```bash
cd /path/to/fastdeploy
./scripts/test_deployment.py --service test_dummy
```

This will:
1. Authenticate with FastDeploy
2. Get a service token for test_dummy
3. Start a deployment
4. Monitor progress in real-time
5. Report final status

### Expected Output

The test should show progress like this:

```
🚀 Deployment Progress:
==================================================
  ✅ Initialize deployment - Starting deployment for test_dummy
  ✅ Validate deployment environment - Completed: Validate deployment environment
  ✅ Clone/update git repository - Completed: Clone/update git repository
  ✅ Install dependencies - Completed: Install dependencies
  ✅ Configure service - Completed: Configure service
  ✅ Setup systemd service - Completed: Setup systemd service
  ✅ Start/restart service - Completed: Start/restart service
  ✅ Run health check - Completed: Run health check
  ✅ Clean up old versions - Completed: Clean up old versions
  ✅ Deployment complete - Completed: Deployment complete
==================================================

🎉 Deployment finished!
✅ Deployment SUCCEEDED
```

## Using as Template

To create a new service based on test_dummy:

1. **Copy the registration playbook**:
   ```bash
   cp playbooks/register-test-dummy.yml playbooks/register-myservice.yml
   ```

2. **Update service details**:
   ```yaml
   vars:
     fd_service_name: "myservice"
     fd_service_description: "My service description"
   ```

3. **Customize the deployment script**:
   - Replace the `fd_runner_content` with your deployment logic
   - Keep the same JSON output format
   - Maintain proper error handling
   - Use realistic step names for your deployment

4. **Register and test**:
   ```bash
   just register-one myservice
   ./scripts/test_deployment.py --service myservice
   ```

## Architecture Integration

### File Locations

After registration, test_dummy creates this structure:

```
/home/fastdeploy/site/services/test_dummy/
├── config.json          # Service metadata for FastDeploy UI
└── deploy.py            # Deployment script (FastDeploy calls this)

/home/deploy/runners/test_dummy/
└── deploy.py            # Source deployment script

/etc/sudoers.d/fastdeploy_test_dummy  # Sudoers rules
```

### Security Model

The test_dummy service follows FastDeploy's security model:

1. **FastDeploy** (fastdeploy user) receives web requests
2. **Creates secure config** in `/var/tmp/` with deployment parameters
3. **Uses sudo** to execute script as `deploy` user
4. **Deploy user** runs script with restricted permissions

### From-Scratch Compatibility

The service works correctly when redeploying infrastructure from scratch because:

1. **Scripts deployed to both locations**:
   - Source: `/home/deploy/runners/test_dummy/deploy.py`
   - Called: `/home/fastdeploy/site/services/test_dummy/deploy.py`

2. **Config references relative path**: `"deploy_script": "deploy.py"`

3. **Proper sync maintained** between both script locations

## Configuration Options

The test_dummy registration supports these configuration options:

```yaml
vars:
  fd_service_name: "test_dummy"
  fd_service_description: "Custom description"
  fd_fastdeploy_root: "/home/fastdeploy/site"  # FastDeploy installation path

  # Custom deployment script (replaces default)
  fd_runner_content: |
    #!/usr/bin/env python3
    # Your custom deployment script here

  # API configuration (optional)
  fd_api_base: "http://localhost:8000"
  fd_api_token: "{{ api_token }}"

  # User configuration
  fd_deploy_user: "deploy"
  fd_fastdeploy_user: "fastdeploy"
```

## Troubleshooting

### Common Issues

1. **Service not found in UI**
   - Check registration completed successfully
   - Run `python commands.py syncservices` in FastDeploy directory
   - Verify `/home/fastdeploy/site/services/test_dummy/config.json` exists

2. **Deployment hangs or fails**
   - Check deploy user permissions
   - Verify sudoers rule exists: `/etc/sudoers.d/fastdeploy_test_dummy`
   - Check systemd service hardening settings (NoNewPrivileges, PrivateTmp)

3. **Permission denied errors**
   - Ensure config files have 0o640 permissions
   - Check deploy user can read config files
   - Verify FastDeploy user can write to `/var/tmp/`

4. **KeyError: 'service_name'**
   - This is the old error pattern - test_dummy now correctly extracts service name from `deploy_script` field
   - If you see this, the deployment script wasn't updated properly

### Debug Commands

```bash
# Check service registration
ls -la /home/fastdeploy/site/services/test_dummy/

# Test script manually
sudo -u deploy /home/deploy/runners/test_dummy/deploy.py --config /tmp/test_config.json

# Check sudoers rule
cat /etc/sudoers.d/fastdeploy_test_dummy

# View FastDeploy logs
journalctl -u fastdeploy -f
```

## Integration with ops-control

The test_dummy service integrates seamlessly with the ops-control workflow:

```bash
# Register (one command)
just register-one test-dummy

# Deploy via FastDeploy UI
# Navigate to https://your-fastdeploy-instance/

# Test deployment programmatically
./scripts/test_deployment.py --service test_dummy
```

The service demonstrates the complete FastDeploy integration pattern that other services can follow for consistent, reliable deployments.
