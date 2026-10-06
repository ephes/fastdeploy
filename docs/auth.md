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

**Permitted Operations**:
- View and manage services
- View deployment history
- Generate service tokens
- Synchronize services from filesystem

### Service Token

**Purpose**: Authenticate services for initiating deployments

**Obtaining**: POST to `/service-token` with user token authentication

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

**Permitted Operations**:
- Start deployments for the specified service
- View deployment details for the service

**Example Workflow**:
1. User logs into web interface with user token
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

**Default Expiration**: 30 minutes

**Permitted Operations**:
- Report step progress for the specific deployment
- Mark deployment as finished

**Usage**: Passed to deployment process via `ACCESS_TOKEN` environment variable

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
