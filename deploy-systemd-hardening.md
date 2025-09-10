# Deploying Systemd Hardening Updates

## Quick Deployment Steps

### 1. Test the Service File Locally First
```bash
# Validate the syntax of the new service file
systemd-analyze verify ansible/deploy.service

# Or if you have access to a test system:
sudo cp ansible/deploy.service /tmp/test-deploy.service
systemd-analyze verify /tmp/test-deploy.service
```

### 2. Deploy Using Ansible

#### Option A: Deploy to Staging First (Recommended)
```bash
cd /Users/jochen/projects/fastdeploy

# Deploy to staging with the updated service file
ansible-playbook -i ansible/hosts.yml ansible/deploy.yml --limit staging

# The playbook will:
# 1. Create symlink from ansible/deploy.service to /etc/systemd/system/deploy.service
# 2. Reload systemd daemon
# 3. Restart the service
```

#### Option B: Deploy to Specific Host (e.g., macmini)
```bash
# Deploy to macmini specifically
ansible-playbook -i ansible/hosts.yml ansible/deploy-macmini.yml

# Or if macmini is in your inventory:
ansible-playbook -i ansible/hosts.yml ansible/deploy.yml --limit macmini
```

### 3. Manual Deployment (If Needed)

If you need to deploy manually or test on a specific server:

```bash
# SSH to the target server
ssh deploy@your-server

# Backup existing service file
sudo cp /etc/systemd/system/deploy.service /etc/systemd/system/deploy.service.backup

# Copy new service file (you'll need to transfer it first)
# Option 1: Via scp from your local machine
scp ansible/deploy.service deploy@your-server:/tmp/

# Then on the server:
sudo cp /tmp/deploy.service /etc/systemd/system/deploy.service

# Reload systemd and restart service
sudo systemctl daemon-reload
sudo systemctl restart deploy.service

# Check status
sudo systemctl status deploy.service
journalctl -u deploy.service -f
```

### 4. Progressive Hardening Deployment

Start with basic hardening, then increase security level:

```bash
# Phase 1: Deploy basic hardening (current ansible/deploy.service)
ansible-playbook -i ansible/hosts.yml ansible/deploy.yml --limit staging

# Monitor for 24-48 hours, check logs:
ssh deploy@staging "journalctl -u deploy.service --since='1 day ago' | grep -i 'permission\|denied'"

# Phase 2: If no issues, deploy to production
ansible-playbook -i ansible/hosts.yml ansible/deploy.yml --limit production

# Phase 3: After validation, upgrade to maximum hardening
# First update the symlink in the playbook to point to deploy-hardened.service
# Then redeploy
```

## Verification After Deployment

### 1. Check Service Status
```bash
# On the target server
sudo systemctl status deploy.service

# Check for any permission errors
journalctl -u deploy.service -n 100 | grep -i "permission\|denied\|failed"
```

### 2. Test Application Functionality
```bash
# Test the API endpoints
curl http://localhost:9999/health
curl http://localhost:9999/api/v1/status

# Check WebSocket connectivity if applicable
# Check database connectivity
```

### 3. Verify Security Hardening
```bash
# Check security score
systemd-analyze security deploy.service

# Verify the hardening directives are active
systemctl show deploy.service | grep -E "PrivateTmp|NoNewPrivileges|ProtectKernel"
```

## Rollback Procedure

If issues occur after deployment:

### Quick Rollback
```bash
# On the affected server
sudo cp /etc/systemd/system/deploy.service.backup /etc/systemd/system/deploy.service
sudo systemctl daemon-reload
sudo systemctl restart deploy.service
```

### Rollback via Ansible
```bash
# First, revert the changes in your local ansible/deploy.service file
git checkout ansible/deploy.service

# Then redeploy
ansible-playbook -i ansible/hosts.yml ansible/deploy.yml --limit affected-host
```

## Troubleshooting Common Issues

### Issue 1: Service Fails to Start
```bash
# Check the exact error
systemctl status deploy.service
journalctl -xe -u deploy.service

# Common fixes:
# - If "Permission denied" on file access, check ReadWritePaths
# - If database connection fails, ensure PrivateNetwork is not set
# - If port binding fails, check capabilities for ports < 1024
```

### Issue 2: Application Can't Write to Directories
```bash
# Add necessary paths to the service file:
# Edit the service file and add under [Service]:
ReadWritePaths=/path/to/writable/directory

# Then reload and restart:
sudo systemctl daemon-reload
sudo systemctl restart deploy.service
```

### Issue 3: Gradual Degradation
```bash
# If the service degrades over time, check resource limits:
systemctl status deploy.service
systemd-cgtop  # Monitor resource usage

# Adjust MemoryMax or TasksMax if needed
```

## Using the Hardened Templates

For new deployments or customization:

```bash
# Use the Ansible template with variables
ansible-playbook -i ansible/hosts.yml ansible/deploy.yml \
  -e "deploy_memory_max=4G" \
  -e "deploy_memory_high=3G" \
  -e "deploy_port=8080"
```

## Monitoring After Deployment

Set up monitoring for:
1. Service restart frequency
2. Memory usage vs limits
3. File descriptor usage
4. Permission denied errors in logs

```bash
# Quick monitoring script
#!/bin/bash
while true; do
  echo "=== $(date) ==="
  systemctl status deploy.service --no-pager | head -n 3
  echo "Memory: $(systemctl show deploy.service -p MemoryCurrent | cut -d= -f2)"
  echo "Tasks: $(systemctl show deploy.service -p TasksCurrent | cut -d= -f2)"
  echo "Restarts: $(systemctl show deploy.service -p NRestarts | cut -d= -f2)"
  sleep 60
done
```

## Next Steps After Deployment

1. ✅ Deploy basic hardening to staging
2. ⏳ Monitor for 48 hours
3. 📊 Collect metrics and logs
4. 🚀 Deploy to production if stable
5. 🔒 Consider upgrading to maximum hardening after validation

## Important Notes

- The current `ansible/deploy.yml` playbook creates a symlink to the service file
- Changes to `ansible/deploy.service` will be reflected after running the playbook
- Always backup the existing service file before making changes
- Test on staging/development before production deployment
- The hardening is backwards compatible - it won't break existing functionality if applied progressively
