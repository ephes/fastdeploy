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

FastDeploy also supports `DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS` (default: `300`) in its `.env`. A deployment is only treated as orphaned once neither its start nor any step activity happened within this delay. This prevents brand-new deployments from being auto-finished before their steps are created, and deployments whose deploy task is still retrying to finish them from being finished early.

Deployments are single-flight per service: starting a deployment while the same service still has an active one returns `409 Conflict`. Orphaned unfinished deployments do not block (they are finished as part of a successful start; a rejected start changes nothing), and deployments older than `DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES` (default: `480`) do not block.

Private deployment configs are read from the validated descriptor with a 1 MiB
UTF-8 byte limit (including growth after opening). The JSON root and `context`
must be objects; `context.env`, when present, must be an object. The required
`deployment_id`, `access_token`, `deploy_script`, `steps_url`,
`deployment_finish_url` and `path_for_deploy` fields must be strings, as must
optional `ssh_auth_sock`. Size, decoding, JSON and shape failures return
`Invalid deployment configuration` without including config values in diagnostics.
The writer enforces the same serialized byte limit before creating a file or
starting a child, so oversized generated configs are recorded as launch failures.
When `DEPLOY_CONFIG_FILE` is set, any read failure stops task startup; only an
unset variable permits the legacy environment fallback.

The launcher supervises its detached child with a cleanup thread. If that thread
cannot start, it sends TERM then, if needed, KILL only to the new child's owned
process group, reaps the leader, and removes its credential config before reporting
launch failure. This exceptional synchronous path allows 100 ms for TERM,
100 ms for KILL and 100 ms for reaping (300 ms total), limiting API-loop delay.
Unconfirmed cleanup is reported with category-only diagnostics. The original startup error is retained as the launch error's cause.
The API records one failed launch and releases the service for a later attempt.

The deploy task starts the deploy script as `sudo -u <SUDO_USER> <script> --config <config file>`. This is an
argument list executed without a shell: `deploy_script` from the service's `config.json` (an absolute path, or a path
below the services directory) is one argument, the path of the script. It is not split into words and shell syntax in
it or in `SUDO_USER` is not interpreted, so a `deploy_script` cannot carry extra arguments or commands. sudo sees the
same command as before, so existing sudoers rules keep matching.

`DEPLOYMENT_MAX_RUNTIME_SECONDS` limits stdout draining, step reporting/retry waits and
process exit from the moment the task owns the created subprocess. Startup precedes
the deadline so cancellation cannot lose the process-group handle. The default is 1800 seconds
(30 minutes); configure a finite value greater than zero and at most 86400 seconds in
the API environment or `.env`. The launcher passes it to the detached task. The elapsed
deadline applies to silent and continuously producing scripts alike. On expiry, the
owned process group is stopped, its secure config is removed and failure is reported
before finishing. Cleanup and final failure/finish reports have their own bounded waits
outside this deadline; it is separate from orphan reconciliation.

At startup, `DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES * 60` must be at least
`DEPLOYMENT_MAX_RUNTIME_SECONDS + 2731`. The allowance covers three 10-second
process teardown waits, two final API retry sequences (each at most eight
10-second attempts plus 1,270 seconds of backoff), and one second for integer JWT
expiry rounding. The default runtime therefore requires at least a 76-minute
deployment token; the default token remains 480 minutes. Shorter combinations
refuse startup. Open-step deployments retain their single-flight protection
through runtime and this finalization allowance, including admission and deletion
checks. This bound covers the runner's permitted waits, not launch latency (API
launch, interpreter start, sudo), unbounded OS scheduling or an external process it
lacks permission to signal; leave some headroom above the minimum. The API passes
`DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES` to the runner process along with the runtime,
so the runner admits the same combination when it imports its settings.

The deploy task owns the deploy script it starts. The script runs in its own process group, and the task waits for
it on every path. Unusual output no longer ends the deployment: bytes that are not valid UTF-8 are replaced with
U+FFFD (a step result containing them is still reported, with the replacement character; any other such line is
skipped like every line that is not a step result), and a line longer than 10 MiB is skipped as a whole, up to its
newline, with one message on the task's stderr. When the task stops reading early (an unexpected error or a cancelled
task), it sends `SIGTERM` to the script's process group and waits up to 10 seconds for every member of the group to
exit, not only the script itself. Members that are still alive then get `SIGKILL`. Only after that does the task
remove the config file and report the failure. Limit: the task runs as the `fastdeploy` user and can only signal
processes it is allowed to signal. A script started through `sudo -u deploy` runs as another user, so the signal may
be refused (this is logged to the task's stderr, and the task does not wait); such a script then ends when it next
writes to its closed output pipe, which happens as soon as the deploy task exits.

The deploy task (the detached `python -m deploy.tasks` process that runs the deploy script) reports each step to
`POST /steps/` and finally calls `PUT /deployments/finish/`. Scripts report a step with the state
`running` when it starts (optional) and with `success` or `failure` when it ends. The task forwards
every named JSON line as a report and does not filter states: a line with any other state, or without
`state` (which defaults to `pending`), receives a non-retried 422 and a dropped-step stderr
diagnostic, and changes nothing.
Each report/finish attempt streams at most 4096 response wire bytes and has a
10-second elapsed budget covering headers, body and closure. Success bodies are discarded without
decoding or logging them; error statuses are checked immediately without reading bodies,
so `4xx` responses remain non-retryable regardless of body size or speed. Oversized bodies and elapsed timeouts count as transport
failures and follow the same retries; every opened response is closed.
Connection errors and `5xx` responses are retried with
exponential backoff (4 attempts per step, 6 for finishing the deployment, starting at 3 seconds), so a short API
restart, for example while fastdeploy deploys itself, does not leave the deployment active.
`DeployTask` retry configuration (`attempts`, `finish_attempts`, `sleep_on_fail`, or
`ATTEMPTS`, `FINISH_ATTEMPTS`, `SLEEP_ON_FAIL` when invoking the task directly)
is validated before the deployment script starts, and on assignment. Attempts must
be integers from 1 through 8, and the initial backoff must be finite from 0 through
10 seconds. Booleans are refused. The request helper also validates its attempt
override and backoff before any client call; invalid inputs raise a validation error
instead of silently succeeding or sleeping. The largest accepted retry sequence
has seven waits totalling 1270 seconds, plus the bounded response attempts; the
deployment runtime deadline still caps reporting while its script runs. A retried step report
that the API had already processed (only the response was lost) is recognized by its name and started timestamp and
changes nothing. `4xx` responses are not
retried. A step that still cannot be reported is dropped and logged to the task's stderr (the fastdeploy service
journal), and the task keeps reading the deploy script output; lines that are not a JSON object with a `name` are
skipped. A JSON object without a `name` is logged to the task's stderr with its size and up to 10 shortened keys,
never its values. When the deploy fails, a "failed step" is reported with the same number of attempts as finishing, and the
deployment is finished afterwards; if finishing fails after a failed deploy, the original error is kept. If the failed
step cannot be reported at all, the deployment is left unfinished instead of being finished as an apparent success,
and it stops blocking new deployments once it is older than `DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`.
If such a deployment has no running or pending steps left (every step was already reported as successful before the
script failed), it is orphaned: once `DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS` passed without activity, the orphan
reconciliation finishes it as failed with a `deployment orphaned` failure step that records the reason (see
[Orphaned deployments](endpoints.md#orphaned-deployments)). The fastdeploy journal ("not finishing the deployment")
has the deploy task's side of it.

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
Service definitions are admitted before any synchronization writes or events.
JSON configs and YAML playbooks reject repeated mapping keys at any depth and more
than one `<<` merge key per mapping; diagnostics do not include configuration
values. Merges follow the YAML merge rules: an explicit key overrides a merged one
and earlier merge sources win over later ones. Ordinary aliases remain supported
within the existing depth/node budget.
An optional `deploy_script` must be a nonblank string without NULs, naming one
executable. Optional `steps` must be a list of objects, each with a nonblank string
`name` of at most 255 characters without NULs. Missing fields retain the default script/placeholder behavior;
unknown service and step fields are preserved. Explicit steps must be valid even
when `ansible_playbook` replaces them with playbook-derived steps. Any invalid
service refuses the entire sync, including when `--force` is used.

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
   deployment_id = config.get('deployment_id')  # id of this deployment as a string, e.g. "42"
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

### Retained Ansible JSON callback

Runners selecting `ansible/callback_plugins/json_cb.py` receive one JSON line per
terminal callback. Each line has a zero-based `position`, UTC `start`/`end`
timestamps (the next observation starts at the preceding end), task `name`,
`state`, `outcome`, `ignore_errors`, `error_message` and `misc` result data.
The states remain compatible with the server:

| Callback | State | Outcome |
| --- | --- | --- |
| OK | `success` | `ok` |
| Failed, including ignored failures | `failure` | `failed` |
| Skipped | `success` | `skipped` |
| Unreachable | `failure` | `unreachable` |

Skipped means no work was required; `outcome` distinguishes it from executed work.
Ignored failures retain `failure` with `ignore_errors: true`; ignoring an Ansible
error does not report that step as successful. Unreachable hosts always fail.
Timing measures the interval between observations, not per-host execution time.

Task `no_log` or result `_ansible_no_log` censors the entire payload before message
extraction/serialization. The name becomes `censored task`, `error_message` is
empty and `misc` contains only a `censored` marker; status, position and timing
remain available. Otherwise Ansible's callback serializer supplies `misc`, omitting
internal and verbosity-controlled fields. Install the updated callback with the
retained runner before its next use; this change does not deploy it.

Run the callback regressions with `uv run pytest tests/unit/json_callback_test.py`.
They use synthetic tasks/results and the development `ansible-core` dependency;
no playbooks or host connections are involved.

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
- **Config security**: [Temporary config ownership and descriptor validation](#temporary-configuration-ownership)
- **Secrets management**: SOPS-encrypted secrets, keys only readable by deploy user
- **No network privileges**: Deploy user cannot make outbound connections

### Temporary configuration ownership

FastDeploy creates mode-0640 regular files owned by its service user in `/var/tmp`.
The deployment user must belong to the file's group to read them; the group has
no write permission. Readers also accept mode 0600 when running as the owner.
The kernel checks access on open, and FastDeploy validates type and mode on that
same descriptor. Symlinks and nonregular files are rejected.

Cleanup only accepts files created by the current process. It retains a descriptor
until cleanup to preserve the file's identity, refuses replacement paths and hard
links, and overwrites the validated descriptor before unlinking. Exit cleanup uses
the same checks. The launcher cleans its config when the detached task exits, or
if launch fails, releasing the retained descriptor. A refused cleanup returns false and logs an error; the replacement
is left intact. Overwriting is best effort and does not guarantee erasure on SSDs
or copy-on-write filesystems.

Keep the config directory and its ancestors under trusted ownership. A custom
directory must not be writable by untrusted users; the default `/var/tmp` must be
root-owned with the sticky bit. Processes with the service user's UID and root
are trusted: POSIX does not offer an atomic inode-conditional unlink, so they must
not rename paths concurrently between the final identity check and unlink.


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
