# Security Issue: Secrets in Environment Variables & --preserve-env

## Issue Description

**Security Concern**: The current deployment process exposes sensitive information (JWT tokens, deployment context) through environment variables when using `sudo --preserve-env`, which contradicts security best practices for secrets handling.

**Reported Issue**: "Secrets in env + --preserve-env contradict your own security rule. Spec 4.2 proposes passing ACCESS_TOKEN, CONTEXT, SSH_AUTH_SOCK, etc. via environment variables and using sudo -u <deploy_user> --preserve-env <script>, but Security §8.2 also requires 'Secrets SHALL NOT appear in process arguments or environment variables visible to other users.'"

## Factual Analysis

### Current Implementation

The security concern is **factually correct**. The current deployment process does expose sensitive information through environment variables:

1. **Environment Variable Creation** (`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:35-51`):
   ```python
   def get_deploy_environment(deployment: Deployment, deploy_script: str) -> dict:
       # ...
       environment = {
           "ACCESS_TOKEN": access_token,  # JWT token exposed
           "DEPLOY_SCRIPT": deploy_script,
           "STEPS_URL": settings.steps_url,
           "DEPLOYMENT_FINISH_URL": settings.deployment_finish_url,
           "CONTEXT": DeploymentContext(**deployment.context).model_dump_json(),  # Sensitive context data
           "PATH_FOR_DEPLOY": settings.path_for_deploy,
       }
       if ssh_auth_sock := os.environ.get("SSH_AUTH_SOCK"):
           environment["SSH_AUTH_SOCK"] = ssh_auth_sock  # SSH socket preserved
   ```

2. **Sudo Command with --preserve-env** (`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:110-112`):
   ```python
   sudo_command = f"sudo -u {settings.sudo_user}"
   deploy_command = str(settings.services_root / self.deploy_script)
   command = f"{sudo_command} --preserve-env {deploy_command}"
   ```

3. **Environment Propagation** (`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:113-121`):
   ```python
   env = os.environ.copy()  # Full environment copied
   env["PATH"] = self.path_for_deploy
   proc = await asyncio.create_subprocess_shell(
       command,
       # ...
       env=env,  # All environment variables passed to subprocess
   )
   ```

### Security Implications

#### 1. Environment Variable Visibility
Environment variables are visible to:
- All processes running under the same user
- Other users with appropriate privileges (ps, /proc filesystem)
- Process monitoring tools
- System administrators via standard Unix utilities

#### 2. Sensitive Data Exposed
- **ACCESS_TOKEN**: JWT tokens containing deployment authorization
- **CONTEXT**: Deployment context that may contain sensitive configuration
- **SSH_AUTH_SOCK**: SSH agent socket (less critical but still sensitive)

#### 3. Attack Vectors
- **Process Enumeration**: `ps auxeww` shows environment variables
- **Proc Filesystem**: `/proc/PID/environ` exposes environment
- **Memory Dumps**: Environment variables may appear in core dumps
- **Log Leakage**: Process spawning may log environment variables

## Root Cause Locations

### Primary Issues

1. **`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:42-46`**:
   - Direct assignment of sensitive data to environment variables
   - ACCESS_TOKEN (JWT) and CONTEXT (deployment data) exposed

2. **`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:112`**:
   - Use of `--preserve-env` flag preserves ALL environment variables
   - No selective environment variable filtering

3. **`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:113-121`**:
   - Full environment copy with sensitive variables passed to subprocess
   - No sanitization or filtering of sensitive environment variables

### Configuration Files
4. **`/Users/jochen/projects/fastdeploy/ansible/fastdeploy_sudoers.template.j2:1`**:
   - `NOPASSWD:SETENV` allows environment variable setting
   - This enables the --preserve-env functionality but also the security risk

## Security Impact Assessment

### Severity: **HIGH**

#### Risk Factors
- **Confidentiality**: HIGH - JWT tokens and deployment context exposed
- **Integrity**: MEDIUM - Compromised tokens could enable unauthorized deployments
- **Availability**: LOW - Direct availability impact minimal
- **Scope**: All deployments running on the system

#### Business Impact
- Unauthorized access to deployment system
- Potential lateral movement in infrastructure
- Compliance violations (secrets handling requirements)
- Trust boundary violations between deployment processes

### Exploitability
- **Attack Complexity**: LOW - Standard Unix tools can enumerate processes
- **Privileges Required**: LOW - Basic system user access sufficient
- **User Interaction**: NONE - Passive information disclosure

## Proposed Solutions

### Solution 1: Secure Configuration File (Recommended)

**Approach**: Pass sensitive data via root-only temporary configuration files

**Implementation**:
```python
# Create secure temp file with 0600 permissions
import tempfile
import json
import os

def create_secure_config(deployment_data: dict) -> str:
    fd, temp_path = tempfile.mkstemp(prefix='deploy_config_', suffix='.json')
    try:
        # Set restrictive permissions before writing
        os.fchmod(fd, 0o600)  # rw-------

        with os.fdopen(fd, 'w') as f:
            json.dump(deployment_data, f)

        return temp_path
    except:
        os.unlink(temp_path)
        raise

# Modified deployment command
command = f"sudo -u {settings.sudo_user} {deploy_command} --config {config_file}"
```

**Pros**:
- No environment variable exposure
- Standard Unix file permissions model
- Temporary file automatically cleaned up
- Backward compatible with minimal script changes

**Cons**:
- File system I/O overhead
- Requires script modification to accept config files
- Temporary file management complexity

### Solution 2: Standard Input (stdin) Configuration

**Approach**: Pass configuration data via stdin as JSON

**Implementation**:
```python
config_data = {
    "access_token": access_token,
    "context": deployment.context,
    "steps_url": settings.steps_url,
    "deployment_finish_url": settings.deployment_finish_url,
}

proc = await asyncio.create_subprocess_shell(
    command,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
    env=filtered_env,  # No sensitive variables
)

await proc.stdin.write(json.dumps(config_data).encode())
await proc.stdin.close()
```

**Pros**:
- No file system artifacts
- No process enumeration exposure
- Clean separation of configuration and execution
- Scales well with configuration complexity

**Cons**:
- Requires significant script refactoring
- Potential stdin buffering issues with large configs
- More complex error handling

### Solution 3: Environment Variable Filtering

**Approach**: Remove --preserve-env and pass only necessary environment variables

**Implementation**:
```python
# Whitelist safe environment variables
safe_env_vars = {
    "PATH": self.path_for_deploy,
    "HOME": os.environ.get("HOME", "/tmp"),
    "LANG": os.environ.get("LANG", "en_US.UTF-8"),
}

# Add SSH_AUTH_SOCK only if needed and safe
if ssh_auth_sock := os.environ.get("SSH_AUTH_SOCK"):
    safe_env_vars["SSH_AUTH_SOCK"] = ssh_auth_sock

# Remove --preserve-env, pass filtered environment
command = f"sudo -u {settings.sudo_user} {deploy_command} --config {config_file}"
proc = await asyncio.create_subprocess_shell(
    command,
    env=safe_env_vars,
    # ...
)
```

**Pros**:
- Immediate security improvement
- Minimal code changes required
- Maintains current architecture
- Easy to audit environment variable usage

**Cons**:
- Still requires alternative method for sensitive data
- May break deployments expecting specific environment variables
- Ongoing maintenance of environment variable whitelist

## Recommendation

### Primary Recommendation: **Solution 1 - Secure Configuration File**

This approach provides the best balance of security, maintainability, and compatibility:

1. **Immediate Security**: Eliminates environment variable exposure
2. **Minimal Changes**: Requires only script argument parsing changes
3. **Standard Practice**: Follows established secure configuration patterns
4. **Auditability**: File-based configs are easier to audit and monitor

### Implementation Steps

1. **Phase 1**: Modify deployment script to accept `--config` parameter
2. **Phase 2**: Update `deploy_steps()` to create secure config files
3. **Phase 3**: Remove `--preserve-env` flag and sensitive environment variables
4. **Phase 4**: Update sudoers to remove `SETENV` requirement
5. **Phase 5**: Add configuration cleanup and error handling

### Security Controls

- Configuration files created with `0600` permissions (owner read/write only)
- Files created in secure temporary directory
- Automatic cleanup after deployment completion
- Logging of configuration file operations (without sensitive content)
- Regular audit of file permissions and cleanup processes

## Testing Considerations

1. **Security Testing**: Verify environment variables no longer contain secrets
2. **Compatibility Testing**: Ensure all deployment scripts work with new config method
3. **Error Handling**: Test cleanup behavior when deployments fail
4. **Permission Testing**: Verify file permissions are correctly set
5. **Performance Testing**: Measure impact of file I/O on deployment speed

## References

- OWASP Secrets Management Guidelines
- CIS Controls: Secure Configuration Management
- NIST SP 800-53: Configuration Management Controls
- fastDeploy Security Architecture Documentation
