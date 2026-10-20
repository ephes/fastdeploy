# Authentication & Authorization

fastDeploy uses JWT-based authentication with four distinct token types, each providing specific authorization scopes. All tokens are signed using HMAC-SHA256 (HS256) and include automatic expiration checking.

## Token Types

### User Token (Access Token)

**Purpose**: Authenticate human users for API and UI access

**Obtaining**: POST `username` and `password` to `/token` endpoint

**Payload Structure**:
```json
{"type": "user", "user": "<username>", "exp": "<expiration>"}
```

**Default Expiration**: 30 minutes

**Failed login limit**: `POST /token` answers `429` with a `Retry-After` header once a user name had
`LOGIN_FAILURE_LIMIT` (default 10) failed attempts from one client address, or one client address had
`LOGIN_ADDRESS_FAILURE_LIMIT` (default 50) failed attempts for any user names, inside
`LOGIN_FAILURE_WINDOW_SECONDS` (default 900). A successful login clears the count for that user name and
address; `LOGIN_FAILURE_LIMIT=0` turns the limit off. The counts are kept in memory by the API process
(a restart clears them; with several worker processes each one counts on its own). The client address is
the one the ASGI server reports: behind a reverse proxy, uvicorn must trust the proxy's forwarded headers
(its default for a proxy on `127.0.0.1`, see `--forwarded-allow-ips`), otherwise every client shares the
proxy's address and the per-address limit applies to all of them together. The password hash check runs
in a worker thread and is also spent on unknown user names, so a login attempt neither blocks the API
nor reveals by its duration whether a user exists.

**Permitted Operations**:
- View and manage services
- View deployment history
- Generate service tokens only if listed in `SERVICE_TOKEN_ADMIN_USERS`
- Synchronize services from filesystem

### Service Token

**Purpose**: Authenticate services for initiating deployments

**Obtaining**: POST to `/service-token` with an administrator user token, or on the server with
`python commands.py issueservicetoken --service S --user U --days N [--origin O]` (prints only the token).

FastDeploy has no stored admin/staff role. `SERVICE_TOKEN_ADMIN_USERS` is an explicit JSON list of
existing user names (for example `SERVICE_TOKEN_ADMIN_USERS='["operator"]'`). It defaults to `[]`:
all logged-in users receive 403 on issuance until an operator configures an administrator.
The check uses the authenticated database user, not claims supplied by the client. The web UI
obtains a service token when starting a run, so non-admin users can still log in and view history
but cannot start new runs through the UI. The services list shows the issuance error and sends
no deployment request when issuance is refused. Existing service tokens keep their expiry, revocation
and legacy-grace behavior; removing an issuer from the list does not revoke their tokens.
The server-local CLI remains an out-of-band administrative operation; `--user` attributes the
token to an existing user and does not grant that user API issuance rights.

**Payload Structure**:
```json
{"type": "service", "service": "<service_name>", "origin": "<origin>", "user": "<creator>", "jti": "<token id>", "exp": "<expiration>"}
```

**Expiration Range**: 1 day by default, at most `SERVICE_TOKEN_MAX_EXPIRE_DAYS` (default 90)

**Revocation**: Every issued service token is recorded in the `service_token` table with its id
(`jti`), service, origin, user and expiry. A service token is only accepted while its record exists,
is not revoked and the user who obtained it still exists. Revoke a token with
`DELETE /service-token/{jti}` (any logged-in user) or `python commands.py revokeservicetoken <jti>`;
`python commands.py listservicetokens` lists the issued tokens. The `jti` is returned when the token
is issued and is also readable from the token payload. Revocation does not affect deployments that
are already running (they use their own deployment token).

**Cleanup**: Every issued token adds a record (the web frontend issues a 1-day token per deployment).
Records of tokens that expired or were revoked more than `SERVICE_TOKEN_RETENTION_DAYS` (default 30)
days ago are deleted whenever a new service token is issued. To clean up explicitly (for example from
a cron job), run `python commands.py purgeservicetokens [--older-than-days N]`. A deleted record's
token is rejected as unknown, just like an expired or revoked one.

**Legacy tokens**: Service tokens issued before revocation support have no `jti` and cannot be
revoked. They are rejected unless `LEGACY_SERVICE_TOKENS_ACCEPTED_UNTIL` is set to a point in time
(ISO 8601, for example `2026-11-01T00:00:00+00:00`; without a timezone UTC is assumed). Until then
they are still accepted if the user who obtained them exists. Use the window to replace them with
new tokens, then unset the setting.

**Legacy token cutover**: every token issued before revocation support (for example Echoport's
`FASTDEPLOY_SERVICE_TOKEN` and the tokens that playbooks minted with `create_access_token`) has no
`jti`. Deploying this release without a grace period makes all of them fail at once. Order:

1. Pick the end of the grace period (an ISO 8601 timestamp with offset) and set
   `LEGACY_SERVICE_TOKENS_ACCEPTED_UNTIL` in the deployed `.env`. With the ops-library
   `fastdeploy_deploy` role (2.31.6 or later) set `fastdeploy_legacy_service_tokens_accepted_until`;
   a hand edit on the host is overwritten by the next deploy.
2. Deploy. Legacy tokens keep working until that point in time.
3. Re-issue every token in use with `python commands.py issueservicetoken` (or `POST /service-token`),
   store each new token where the old one was, roll out the consumers, and check that each still
   triggers deployments. `python commands.py listservicetokens` shows what was issued.
4. Before the grace period ends, unset the setting (set the role variable back to empty) and deploy
   again. After that, or once the timestamp has passed, tokens without `jti` are rejected with 401.

**Permitted Operations**:
- Start deployments for the specified service
- View deployment details for the service

**Example Workflow**:
1. Administrator logs into web interface with user token
2. Generates service token for specific service
3. Stores service token in CI/CD system (e.g., GitHub Secrets)
4. CI/CD uses service token to trigger deployments after successful builds

### Deployment Token

**Purpose**: Authenticate deployment processes for status reporting

**Generation**: Automatically created when deployment starts

**Payload Structure**:
```json
{"type": "deployment", "deployment": "<deployment_id>", "exp": "<expiration>"}
```

**Default Expiration**: 480 minutes (`DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`)

**Permitted Operations**:
- Report step progress for the specific deployment
- Mark deployment as finished

**Usage**: Written as `access_token` to the deployment's config file (mode `0640`), which the deploy
task reads and passes to the deploy script with `--config`; it is not passed in an environment variable

### Config Token

**Purpose**: Enable service discovery for deployed services

**Use Cases**: Services like logging, monitoring, or backup systems that need to discover and interact with other deployed services

**Payload Structure**:
```json
{"type": "config", "<custom_fields>", "exp": "<expiration>"}
```

**Permitted Operations**:
- Query list of deployed services and their configurations

## Security Considerations

- All API endpoints except `/token` require authentication
- Invalid or expired tokens result in HTTP 401 Unauthorized
- Token validation includes signature verification and expiration checking
- Tokens should be transmitted over HTTPS in production
- Service registration requires out-of-band administrative access (cannot be done via API)

JWT signing and verification use PyJWT with an explicit HMAC algorithm (`HS256` by default;
`TOKEN_SIGN_ALGORITHM` also accepts `HS384` and `HS512`). Existing python-jose tokens remain
valid with the same secret and algorithm. No asymmetric signing dependency is needed.
Expiry retains the previous whole-second boundary; tokens without `exp` remain accepted
by the decoder, while every issuance path adds `exp`. Service-token revocation and the
legacy grace deadline remain unchanged.

## Restore input policy

All deploy, backup and restore runs use the single `POST /deployments/` endpoint. The verified
service token selects the service and its registered executable. Body or query service identifiers
cannot select another service. Recorded tokens must also match the service and user in their record.

Echoport runners in ops-library's `echoport_backup` role read `context.env.ECHOPORT_ACTION`
(`restore` selects restore; some variants strip whitespace and lowercase it), `ECHOPORT_BUCKET`
and `ECHOPORT_KEY`. FastDeploy uses the normalized action to detect restores. FastDeploy checks these inputs
before storing a deployment, publishing events or launching a runner. A restore, or any supplied
`ECHOPORT_KEY`, requires an explicit policy keyed by the **authenticated service name**:

```shell
RESTORE_POLICIES='{"echoport-backup":{"bucket":"backups","prefix":"echoport/"}}'
```

Use the actual registered service name and its backup object prefix; they need not have the same
name. Prefixes end in `/` and consist of ASCII letters, digits, `_`, `-` and `/` between nonempty
components. The request must explicitly supply the configured bucket and a key below that prefix.
Keys allow ASCII letters, digits, `_`, `-`, `.`, and `/` between nonempty components; `..` anywhere,
`.` components, absolute paths, URL schemes, percent encoding, backslashes and control characters
are rejected. Missing policy, missing/wrong bucket or invalid/missing key returns 422 with a clear
error and starts nothing. Defaults deny restores; ordinary deploys and backups without an archive
key need no policy. This policy does not validate archive contents or replace runner-side checksum,
extraction and destination checks. Other runner-specific context remains subject to the registered
runner's own validation. The `fastdeploy_register_service` role also passes `context.env` to its
registered deployment runner; this change does not alter those roles or allow a different executable.

Deployment requires configuring `SERVICE_TOKEN_ADMIN_USERS` in the managed application environment,
and `RESTORE_POLICIES` for each service that should support restores, then restarting FastDeploy.
No database migration or token rotation is required. Existing tokens are subject to the restore
input policy on their next restore request. No ops-library changes are included.
