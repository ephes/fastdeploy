# Security Issue: Process Isolation and systemd Sandboxing

## Issue Description

**Security Concern**: The current deployment process relies solely on "different user + sudo" for isolation, which provides limited protection against privilege escalation and system compromise. The recommendation is to strengthen isolation using systemd sandboxing features to constrain filesystem access, network capabilities, and system resources.

**Review Feedback**: "Strengthen isolation of the deploy process. Right now you rely on 'different user + sudo' (good), but you can cheaply add systemd sandboxing to constrain filesystem/network/capabilities. The recommendation is to execute via systemd-run (transient unit) with a hardened profile including DynamicUser, PrivateTmp, ProtectSystem, ProtectHome, NoNewPrivileges, RestrictAddressFamilies, and ReadWritePaths directives."

## Factual Analysis

### Current Implementation

The security concern is **factually correct**. The current deployment isolation relies primarily on user separation with minimal additional constraints:

1. **Process Execution** (`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:110-121`):
   ```python
   sudo_command = f"sudo -u {settings.sudo_user}"
   deploy_command = str(settings.services_root / self.deploy_script)
   command = f"{sudo_command} --preserve-env {deploy_command}"
   # ...
   proc = await asyncio.create_subprocess_shell(
       command,
       stdout=asyncio.subprocess.PIPE,
       stderr=asyncio.subprocess.STDOUT,
       limit=MAX_ASYNCIO_STDOUT_SIZE,
       env=env,
   )
   ```

2. **Sudo Configuration** (`/Users/jochen/projects/fastdeploy/ansible/fastdeploy_sudoers.template.j2:1-4`):
   ```
   deploy ALL = (root) NOPASSWD:SETENV: {{ services_path }}/fastdeploy/deploy.sh
   Cmnd_Alias RESTART_CMDS = /usr/bin/systemctl start deploy, /usr/bin/systemctl stop deploy
   deploy ALL=(ALL) NOPASSWD: RESTART_CMDS
   ```

3. **Deployment Script Execution**: Deployment scripts run Ansible playbooks with full system access:
   - Scripts use `os.execve()` to run ansible-playbook
   - Ansible playbooks create users, manage databases, install services
   - Full filesystem and network access available

### Current Isolation Mechanisms

**Strengths**:
- User separation via sudo (different user context)
- Process execution in separate session (`start_new_session=True`)
- Sudoers rules limit executable commands

**Weaknesses**:
- No filesystem sandboxing
- No network restrictions
- No capability restrictions
- Full access to system resources
- No dynamic user isolation
- Environment variable preservation risks (--preserve-env)

## Root Cause Locations

### Primary Issues

1. **`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:110-121`**:
   - Direct subprocess execution with minimal isolation
   - No systemd sandboxing features used
   - Full system access available to deployment processes

2. **`/Users/jochen/projects/fastdeploy/ansible/fastdeploy_sudoers.template.j2:1`**:
   - Sudoers configuration allows SETENV, enabling environment variable manipulation
   - No additional restrictions on process capabilities

3. **Deployment Scripts** (e.g., `/Users/jochen/projects/fastdeploy/services_development/single_cast_hosting/deploy.py:42`):
   - Scripts execute with full user privileges
   - Ansible playbooks run with extensive system access
   - No constraint on resource usage or system interactions

### Configuration Dependencies

4. **Ansible Playbooks** (e.g., `/Users/jochen/projects/fastdeploy/services_development/single_cast_hosting/playbook.yml`):
   - Create system users and databases
   - Manage systemd services
   - Modify system configuration files
   - All operations require elevated privileges

## Security Impact Assessment

### Severity: **MEDIUM-HIGH**

#### Risk Factors
- **Confidentiality**: MEDIUM - Process can access more files than necessary
- **Integrity**: HIGH - Compromised deployment process could modify system files
- **Availability**: MEDIUM - Resource exhaustion or system service disruption possible
- **Scope**: All deployment operations on the system

#### Business Impact
- **Privilege Escalation**: Compromised deployment scripts could gain broader system access
- **Lateral Movement**: Limited filesystem isolation enables broader system exploration
- **Resource Exhaustion**: No resource limits could impact system availability
- **Attack Surface**: Large attack surface with full user-level system access

### Exploitability
- **Attack Complexity**: LOW - Standard deployment script compromise
- **Privileges Required**: MEDIUM - Requires deployment script execution
- **User Interaction**: NONE - Automatic during deployments
- **Attack Vector**: Code injection in deployment scripts or Ansible playbooks

## Security Benefits of systemd Sandboxing

### Defense in Depth
systemd sandboxing provides multiple isolation layers beyond user separation:

1. **Filesystem Isolation**:
   - `ProtectSystem=strict`: Make system directories read-only
   - `ProtectHome=true`: Hide home directories
   - `PrivateTmp=true`: Private /tmp namespace
   - `ReadWritePaths=`: Explicitly allowed writable paths

2. **Network Restrictions**:
   - `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`: Limit network protocols
   - `PrivateNetwork=false`: Keep network access for deployment needs

3. **Capability Restrictions**:
   - `NoNewPrivileges=true`: Prevent privilege escalation
   - `CapabilityBoundingSet=`: Limit available capabilities
   - `AmbientCapabilities=`: Remove ambient capabilities

4. **Resource Controls**:
   - `DynamicUser=true`: Temporary user isolation
   - `RemoveIPC=true`: Clean up IPC objects
   - Memory and CPU limits via systemd

## Proposed systemd Sandboxing Implementation

### Solution 1: systemd-run with Hardened Profile (Recommended)

**Approach**: Execute deployment processes via systemd-run with a comprehensive security profile

**Implementation**:
```python
# Modified deploy_steps method in tasks.py
async def deploy_steps(self):
    # Build systemd-run command with sandboxing
    systemd_run_args = [
        "systemd-run",
        "--uid=deploy",
        "--gid=deploy",
        "--property=DynamicUser=false",  # Use deploy user instead
        "--property=PrivateTmp=true",
        "--property=ProtectSystem=strict",
        "--property=ProtectHome=true",
        "--property=NoNewPrivileges=true",
        "--property=RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "--property=ReadWritePaths=/var/log/deploy /tmp/deploy",
        "--property=MemoryMax=2G",
        "--property=CPUQuota=50%",
        "--setenv=PATH=" + self.path_for_deploy,
        "--",
        str(settings.services_root / self.deploy_script)
    ]

    # Create secure config file for sensitive data
    config_file = await self._create_secure_config()
    systemd_run_args.append(f"--config={config_file}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *systemd_run_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=MAX_ASYNCIO_STDOUT_SIZE,
        )
        # ... rest of method unchanged
    finally:
        await self._cleanup_secure_config(config_file)

async def _create_secure_config(self) -> str:
    """Create a secure configuration file for sensitive deployment data."""
    config_data = {
        "access_token": self.access_token,
        "context": self.context.model_dump(),
        "steps_url": self.steps_url,
        "deployment_finish_url": self.deployment_finish_url,
    }

    # Create temp file with restrictive permissions
    fd, temp_path = tempfile.mkstemp(
        prefix='deploy_config_',
        suffix='.json',
        dir='/tmp/deploy'  # Controlled directory
    )

    try:
        os.fchmod(fd, 0o600)  # Owner read/write only
        with os.fdopen(fd, 'w') as f:
            json.dump(config_data, f)
        return temp_path
    except:
        os.unlink(temp_path)
        raise

async def _cleanup_secure_config(self, config_file: str):
    """Securely remove configuration file."""
    try:
        # Overwrite with random data before deletion
        with open(config_file, 'wb') as f:
            f.write(os.urandom(os.path.getsize(config_file)))
        os.unlink(config_file)
    except OSError:
        pass  # File already removed
```

**Modified Sudoers Configuration**:
```
# Remove SETENV capability, add systemd-run permission
deploy ALL = (root) NOPASSWD: /usr/bin/systemd-run
deploy ALL = (root) NOPASSWD: /usr/bin/systemctl start deploy, /usr/bin/systemctl stop deploy
```

**Advantages**:
- Comprehensive sandboxing with multiple isolation layers
- Resource limits prevent system resource exhaustion
- Filesystem restrictions limit attack surface
- No environment variable exposure
- Temporary configuration files with secure handling
- Standard systemd tooling, well-tested and maintained

**Trade-offs**:
- Requires systemd (Linux only)
- Additional complexity in process management
- Potential compatibility issues with existing deployment scripts
- Resource limits may need tuning based on deployment requirements

### Solution 2: Custom systemd Service Template

**Approach**: Define a systemd service template for deployment execution

**Implementation**:
```ini
# /etc/systemd/system/fastdeploy-runner@.service
[Unit]
Description=fastDeploy Runner for %i
After=network.target

[Service]
Type=oneshot
User=deploy
Group=deploy
DynamicUser=false
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
NoNewPrivileges=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/log/deploy /tmp/deploy
MemoryMax=2G
CPUQuota=50%
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/fastdeploy/services/%i/deploy.py --config=/tmp/deploy/%i.config
```

**Advantages**:
- Persistent configuration in systemd units
- Fine-grained control over sandboxing parameters
- Easy to audit and modify security settings
- Integration with systemd logging and monitoring

**Disadvantages**:
- Requires systemd unit management
- Less dynamic than systemd-run approach
- Template files need maintenance
- Service name collision potential

## Implementation Complexity Analysis

### Development Effort: **MEDIUM**

#### Required Changes
1. **Core Process Execution** (2-3 days):
   - Modify `deploy_steps()` method to use systemd-run
   - Implement secure configuration file handling
   - Update error handling for systemd execution

2. **Configuration Management** (1-2 days):
   - Remove environment variable usage from deployment scripts
   - Add configuration file parsing to deployment scripts
   - Update Ansible variable passing mechanisms

3. **Infrastructure Updates** (1 day):
   - Update sudoers configuration
   - Create deployment directory structure
   - Update deployment script permissions

4. **Testing and Validation** (2-3 days):
   - Test sandboxing effectiveness
   - Validate deployment functionality
   - Performance impact assessment
   - Security testing and verification

#### Dependencies
- **systemd availability**: Linux systems with systemd (current target)
- **Deployment script modifications**: All scripts must support configuration files
- **Ansible compatibility**: Ensure playbooks work within constraints
- **Resource limit tuning**: Determine appropriate memory/CPU limits

### Compatibility Considerations

#### Breaking Changes
- Deployment scripts must be modified to read configuration files
- Environment variable dependencies must be eliminated
- File system access patterns may need adjustment

#### Migration Path
1. **Phase 1**: Implement configuration file support in deployment scripts
2. **Phase 2**: Add systemd-run execution alongside existing method
3. **Phase 3**: Enable sandboxing features incrementally
4. **Phase 4**: Remove legacy environment variable method
5. **Phase 5**: Full security hardening deployment

## Recommendation

### Primary Recommendation: **Solution 1 - systemd-run with Hardened Profile**

This approach provides the best balance of security, maintainability, and implementation simplicity:

1. **Immediate Security Improvement**: Significant reduction in attack surface
2. **Incremental Implementation**: Can be deployed gradually with fallback options
3. **Standard Tooling**: Uses well-established systemd features
4. **Resource Protection**: Prevents resource exhaustion attacks
5. **Audit-friendly**: Clear isolation boundaries and configuration

### Implementation Priority

1. **High Priority**: Filesystem and capability restrictions
   - `ProtectSystem=strict`
   - `NoNewPrivileges=true`
   - `PrivateTmp=true`

2. **Medium Priority**: Resource limits and network restrictions
   - Memory and CPU quotas
   - `RestrictAddressFamilies`

3. **Low Priority**: Advanced isolation features
   - `ProtectKernelModules=true`
   - `ProtectKernelTunables=true`

### Security Controls

- **Configuration Security**: Secure temporary file handling with restrictive permissions
- **Process Monitoring**: Integration with systemd logging and audit systems
- **Resource Management**: Configurable limits based on deployment requirements
- **Fallback Mechanisms**: Graceful degradation if systemd features unavailable
- **Regular Auditing**: Periodic review of sandboxing effectiveness

## Testing Considerations

1. **Functional Testing**: Verify all existing deployment scenarios work within sandbox
2. **Security Testing**: Validate isolation boundaries and escape prevention
3. **Performance Testing**: Measure impact on deployment speed and resource usage
4. **Compatibility Testing**: Ensure Ansible playbooks function correctly
5. **Failure Testing**: Verify error handling and cleanup in failure scenarios

## References

- **systemd Documentation**: systemd.exec(5) man page for sandboxing options
- **NIST SP 800-53**: System and Services Acquisition controls
- **OWASP Application Security Architecture**: Process isolation guidelines
- **systemd Security Features**: https://systemd.io/SECURITY/
- **Linux Security Modules**: Documentation on capability-based security
