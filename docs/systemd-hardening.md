# Systemd Security Hardening Guide for FastDeploy

## Overview

This document describes the systemd security hardening implementation for FastDeploy services. We provide three levels of hardening to balance security with compatibility.

## Hardening Levels

### Level 1: Basic (Compatible) - `deploy.service`
Recommended for initial deployment and testing. These settings are widely compatible and unlikely to break functionality.

### Level 2: Standard (Balanced) - `deploy-standard.service`
Recommended for production deployments with good security/compatibility balance.

### Level 3: Maximum (Strict) - `deploy-hardened.service`
Maximum security for high-risk environments. May require additional configuration.

## Implementation Status

- ✅ Basic hardening implemented in `ansible/deploy.service`
- ✅ Template with hardening in `ansible/templates/deploy.macmini.service.j2`
- ✅ Maximum hardening available in `ansible/deploy-hardened.service`
- ✅ Ansible template for customization in `ansible/templates/fastdeploy-hardened.service.j2`
- ✅ **Production Issue Resolved**: Deployment subprocess architecture incompatible with `NoNewPrivileges=true`

## Critical Compatibility Issues Discovered

### FastDeploy Subprocess Architecture Conflict (September 2025)

**Issue**: FastDeploy's deployment architecture requires privilege escalation through `sudo`, which conflicts with strict systemd hardening.

**Architecture**:
```
FastDeploy Service (fastdeploy user)
    ↓ creates subprocess
Deployment Process
    ↓ sudo -u deploy
Deploy User (deploy user)
    ↓ executes
Ansible/Shell Commands
```

**Root Cause**: `NoNewPrivileges=true` prevents any process from gaining additional privileges, even through legitimate tools like `sudo`. This caused deployment subprocesses to fail silently with:
```
"The 'no new privileges' flag is set, which prevents sudo from running as root"
```

**Resolution**: FastDeploy systemd service **must** use:
```ini
NoNewPrivileges=false
PrivateTmp=false
```

**Security Implications**:
- FastDeploy service can gain privileges through sudo (required for operation)
- Subprocess isolation is reduced due to shared temp directory access
- This is an architectural requirement, not a security weakness

### Related Permission Issues Fixed

1. **Config File Permissions**: Changed from `0o600` to `0o640` to allow group access
2. **Cross-User File Access**: Updated validation from strict UID checking to readability verification
3. **Temp Directory Isolation**: Moved from `/tmp` to `/var/tmp` and disabled `PrivateTmp`

## Security Features by Category

### 1. Filesystem Protection

#### Basic Level
```ini
# PrivateTmp=false       # DISABLED for FastDeploy - subprocess needs shared temp access
ProtectSystem=full      # /usr, /boot, /efi read-only
ProtectHome=read-only   # Home directories read-only
```

**⚠️ Critical Note**: FastDeploy **cannot** use `PrivateTmp=true` because deployment subprocesses need access to shared configuration files in `/var/tmp`.

#### Maximum Level
```ini
ProtectSystem=strict    # Everything read-only except specified paths
ReadWritePaths=/home/deploy/site/var /home/deploy/site/logs
ReadOnlyPaths=/home/deploy/site/bin /home/deploy/site/src
```

### 2. Process & Privilege Restrictions

#### All Levels
```ini
# NoNewPrivileges=false  # REQUIRED for FastDeploy - subprocess needs sudo
User=deploy             # Run as non-root user
Group=deploy            # Run with non-root group
```

**⚠️ Critical Note**: FastDeploy **cannot** use `NoNewPrivileges=true` due to its subprocess architecture requiring `sudo -u deploy` for security isolation.

#### Maximum Level Additional
```ini
PrivateUsers=yes        # User namespace isolation
RemoveIPC=yes           # Clean IPC objects on stop
PrivateMounts=yes       # Mount namespace isolation
```

### 3. Kernel Protection

#### Basic Level
```ini
ProtectKernelTunables=yes  # Protect kernel tunables
ProtectKernelModules=yes   # Prevent module loading
ProtectControlGroups=yes   # Protect cgroup hierarchy
```

#### Maximum Level Additional
```ini
ProtectKernelLogs=yes       # Protect kernel logs
ProtectClock=yes            # Prevent clock changes
ProtectHostname=yes         # Prevent hostname changes
ProtectProc=invisible       # Hide other processes
ProcSubset=pid              # Limit /proc visibility
```

### 4. Network Restrictions

#### Basic Level
```ini
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
```

#### Maximum Level (Optional)
```ini
IPAddressDeny=any
IPAddressAllow=localhost
IPAddressAllow=10.0.0.0/8
```

### 5. System Call Filtering

#### Maximum Level Only
```ini
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources @reboot @swap
SystemCallErrorNumber=EPERM
SystemCallArchitectures=native
```

### 6. Resource Limits

#### All Levels
```ini
LimitNOFILE=65536       # File descriptor limit
LimitNPROC=4096         # Process limit
MemoryMax=2G            # Maximum memory usage
```

#### Maximum Level Additional
```ini
MemoryHigh=1G           # Soft memory limit
TasksMax=100            # Maximum number of tasks
MemoryDenyWriteExecute=yes  # Prevent JIT code
```

### 7. Device Access

#### Maximum Level Only
```ini
PrivateDevices=yes      # No device access
DevicePolicy=closed     # Deny all devices
LockPersonality=yes     # Lock execution domain
```

## Deployment Instructions

### 1. Test Basic Hardening First
```bash
# Copy basic hardened service
sudo cp ansible/deploy.service /etc/systemd/system/fastdeploy.service
sudo systemctl daemon-reload
sudo systemctl restart fastdeploy
sudo systemctl status fastdeploy
```

### 2. Verify Functionality
```bash
# Check service logs
journalctl -u fastdeploy -f

# Test API endpoints
curl http://localhost:9999/health

# Check for permission errors
journalctl -u fastdeploy | grep -i "permission\|denied"
```

### 3. Upgrade to Stricter Hardening
```bash
# If basic works, try maximum hardening
sudo cp ansible/deploy-hardened.service /etc/systemd/system/fastdeploy.service
sudo systemctl daemon-reload
sudo systemctl restart fastdeploy
```

## Troubleshooting

### Critical Issue: Deployments Succeed but No Steps Execute

**Symptoms**:
- Deployment shows as "SUCCEEDED" in FastDeploy UI
- No deployment steps are created or executed
- Database shows deployment record but no associated steps
- No error messages in logs

**Root Cause**: `NoNewPrivileges=true` silently blocks subprocess `sudo` usage

**Diagnosis Steps**:
1. **Check deployment subprocess logs**:
   ```bash
   journalctl -u fastdeploy -f
   # Look for: "The 'no new privileges' flag is set, which prevents sudo from running as root"
   ```

2. **Add debug logging** to `src/deploy/tasks.py`:
   ```python
   # Temporary debug logging in deploy_steps()
   print(f"DEBUG: Creating subprocess with command: {command}")
   print(f"DEBUG: Subprocess created successfully with PID: {proc.pid}")
   ```

3. **Test subprocess manually**:
   ```bash
   sudo -u fastdeploy sudo -u deploy echo "test"
   # Should work from shell but fail from systemd service
   ```

**Solution**: Update systemd service configuration:
```ini
NoNewPrivileges=false
PrivateTmp=false
```

### Common Issues and Solutions

#### 1. Service Fails to Start
```bash
# Check which security feature is blocking
systemd-analyze security fastdeploy.service
```

#### 2. Subprocess Permission Issues (FastDeploy Specific)
- **Config files not readable by deploy user**: Change permissions to `0o640`
- **PrivateTmp isolation**: Disable `PrivateTmp` and use `/var/tmp` for config files
- **Sudo blocking**: Ensure `NoNewPrivileges=false` for deployment subprocess architecture

#### 3. Permission Denied Errors
- Check `ReadWritePaths` includes all directories the service needs to write to
- Verify `ProtectSystem` level is appropriate
- Consider disabling `PrivateUsers` if UID mapping issues occur

#### 4. Network Connection Issues
- Remove `IPAddressDeny` restrictions
- Check `RestrictAddressFamilies` includes needed protocols
- Verify firewall rules aren't conflicting

#### 5. Database Connection Failures
- Ensure `PrivateNetwork=no` (not set means no)
- Check `RestrictAddressFamilies` includes AF_UNIX for local sockets
- Verify database socket path is accessible

### Debugging Commands

```bash
# Analyze security level
systemd-analyze security fastdeploy.service

# Test configuration
systemd-analyze verify /etc/systemd/system/fastdeploy.service

# View effective configuration
systemctl show fastdeploy.service

# Check service environment
sudo -u deploy systemctl show-environment

# Test with reduced security (temporary)
sudo systemd-run --uid=deploy --gid=deploy \
  --property=PrivateTmp=no \
  --property=ProtectSystem=no \
  /home/deploy/site/bin/deploy.py
```

## Progressive Hardening Strategy

### Phase 1: Basic (Week 1)
Deploy with `deploy.service` configuration:
- Basic filesystem protection
- No privilege escalation
- Kernel protection
- Resource limits

### Phase 2: Standard (Week 2)
Add after testing:
- Stricter filesystem protection
- Namespace isolation
- Basic system call filtering

### Phase 3: Maximum (Week 3-4)
Full hardening after thorough testing:
- Complete system call filtering
- Network restrictions
- Device isolation
- Memory execution prevention

## Monitoring

### Key Metrics to Monitor
1. Service restart frequency
2. Memory usage vs limits
3. File descriptor usage
4. Permission denied errors in logs
5. System call filter violations

### Alerting Rules
```yaml
# Example Prometheus rules
- alert: FastDeployHighMemory
  expr: process_resident_memory_bytes{job="fastdeploy"} > 1.5e9
  for: 5m

- alert: FastDeployRestartLoop
  expr: rate(systemd_unit_restarts_total{name="fastdeploy.service"}[5m]) > 0.2
  for: 10m
```

## Security Validation

### Run Security Analysis
```bash
# Analyze current security level
systemd-analyze security fastdeploy.service

# Target scores:
# Basic: 4.0 - 6.0 (MEDIUM)
# Standard: 2.0 - 4.0 (OK)
# Maximum: < 2.0 (GOOD)
```

### Security Checklist
- [ ] Service runs as non-root user
- [ ] Private tmp enabled
- [ ] No new privileges flag set
- [ ] Kernel protections enabled
- [ ] Resource limits configured
- [ ] Appropriate filesystem protections
- [ ] System call filtering (maximum only)
- [ ] Network restrictions (if applicable)
- [ ] Memory execution prevention (maximum only)

## References

- [systemd.exec Documentation](https://www.freedesktop.org/software/systemd/man/systemd.exec.html)
- [systemd Security Features](https://systemd.io/SECURITY_FEATURES/)
- [systemd Hardening Guide](https://gist.github.com/ageis/f5595e59b1cddb1513d1b425a323db04)
- [RHEL Security Guide](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/html/security_hardening/index)

## Next Steps

1. Deploy basic hardening to staging environment
2. Monitor for 48 hours
3. Address any compatibility issues
4. Gradually increase hardening level
5. Document any service-specific requirements
6. Create automated tests for security features
