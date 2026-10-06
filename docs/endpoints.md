# API Endpoints

Complete reference of all fastDeploy API endpoints, their authentication requirements, and usage.

## Authentication Endpoints

### POST /token
**Purpose**: Authenticate users and obtain access token
**Authentication**: None (username/password in body)
**Request Body**:
```
application/x-www-form-urlencoded
username=<username>&password=<password>
```
**Response**:
```json
{"access_token": "<jwt>", "token_type": "bearer"}
```

### POST /service-token
**Purpose**: Generate service token for deployments
**Authentication**: User token required
**Request Body**:
```json
{
  "service": "<service_name>",
  "origin": "<origin_identifier>",
  "expiration_in_days": 1
}
```
`expiration_in_days` defaults to 1 and may be at most `SERVICE_TOKEN_MAX_EXPIRE_DAYS` (default 90).
The token is recorded with its id (`jti`) so it can be revoked.

**Response**:
```json
{"service_token": "<jwt>", "token_type": "bearer", "jti": "<token id>", "expires_at": "<datetime>"}
```

### DELETE /service-token/{jti}
**Purpose**: Revoke a service token. Deployments can no longer be started with it
**Authentication**: User token required
**Response** (revoking an already revoked token succeeds again and keeps the first time):
```json
{"detail": "Service token <jti> revoked", "jti": "<jti>", "revoked_at": "<datetime>"}
```
**404 Not Found**: no service token with this id was issued

### GET /users/me
**Purpose**: Get current authenticated user
**Authentication**: User token required
**Response**:
```json
{"id": 1, "name": "username"}
```

## Service Management Endpoints

### GET /services/
**Purpose**: List all registered services
**Authentication**: User token required
**Response**:
```json
[
  {
    "id": 1,
    "name": "service_name",
    "data": {
      "deploy_script": "deploy.sh",
      "description": "Service description",
      "steps": [{"name": "step1"}]
    }
  }
]
```

### GET /services/names/
**Purpose**: List available service names from filesystem
**Authentication**: User token required
**Response**:
```json
["service1", "service2", "service3"]
```

### POST /services/sync
**Purpose**: Synchronize filesystem services to database
**Authentication**: User token required
**Query Parameters**: `force` (optional, default `false`)

Services that have no directory in the services directory are deleted together with all of their
deployments and steps. Two guards protect against wiping the history by accident:

- The sync is refused with **409 Conflict** when the services directory lists no services while the
  database has some, or when more than half of the services in the database would be deleted.
  Nothing is changed. Pass `force=true` to delete them anyway.
  ```json
  {"detail": {"message": "...", "would_delete": ["service1"], "total": 1}}
  ```
- A service with a running deployment is never deleted, not even with `force=true`. It is reported
  in `skipped` and removed by a later sync once the deployment has finished.

The web frontend's sync button shows a refusal, including the services that would be deleted,
and offers a "force sync" button that retries with `force=true` after a confirmation dialog.

**Response**:
```json
{
  "detail": "Services synced",
  "updated": ["added_or_changed_service"],
  "deleted": ["removed_service"],
  "skipped": [{"name": "busy_service", "reason": "deployment 42 is still running"}]
}
```

### DELETE /services/{service_id}
**Purpose**: Remove service from database
**Authentication**: User token required
**Response**:
```json
{"detail": "Service 1 deleted"}
```

## Deployment Endpoints

### POST /deployments/
**Purpose**: Initiate new deployment
**Authentication**: Service token required
**Request Body**:
```json
{
  "env": {
    "key": "value"  // Optional deployment context
  }
}
```
**Response**:
```json
{
  "id": 1,
  "service_id": 1,
  "started": "2024-01-01T12:00:00Z",
  "details": "/deployments/1"
}
```
**Single-flight per service**: only one deployment per service runs at a time. If the
service still has an active deployment, the request is rejected with **409 Conflict** and no
deployment is created or started. The response names the running deployment:
```json
{
  "detail": {
    "message": "Deployment 41 is still running for service myservice",
    "deployment_id": 41
  }
}
```
Orphaned unfinished deployments of the service (no running/pending steps and older than
`DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS`) do not block: they are finished as part of a
successful start, so a stale row cannot wedge the service. A rejected (409) start changes nothing. Unfinished deployments started longer ago than the deployment token
lifetime (`DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`, default 480) can no longer report or finish
and do not block new deployments either. Concurrent starts for the same service are serialized
by a database row lock on the service, so exactly one of them succeeds.

### GET /deployments/
**Purpose**: List all deployments
**Authentication**: User token required
**Response**:
```json
[
  {
    "id": 1,
    "service_id": 1,
    "origin": "github",
    "user": "username",
    "started": "2024-01-01T12:00:00Z",
    "finished": "2024-01-01T12:05:00Z"
  }
]
```

### GET /deployments/{deployment_id}
**Purpose**: Get deployment details with steps
**Authentication**: Service token required (must match deployment's service)
**Response**:
```json
{
  "id": 1,
  "service_id": 1,
  "started": "2024-01-01T12:00:00Z",
  "finished": null,
  "steps": [
    {
      "id": 1,
      "name": "step1",
      "state": "success",
      "message": "Step completed"
    }
  ]
}
```

### PUT /deployments/finish/
**Purpose**: Mark deployment as complete
**Authentication**: Deployment token required
**Response**:
```json
{"detail": "Deployment 1 finished"}
```

## Step Management Endpoints

### POST /steps/
**Purpose**: Report step progress
**Authentication**: Deployment token required
**Request Body**:
```json
{
  "name": "step_name",
  "state": "pending|running|success|failure",
  "message": "Optional status message",
  "error_message": "Error details if failure"
}
```
**Response**:
```json
{"detail": "step processed"}
```

### GET /steps/
**Purpose**: List steps for a deployment
**Authentication**: User token required
**Query Parameters**: `?deployment_id=1`
**Response**:
```json
[
  {
    "id": 1,
    "name": "step1",
    "state": "success",
    "message": "Step completed",
    "started": "2024-01-01T12:00:00Z",
    "finished": "2024-01-01T12:01:00Z"
  }
]
```

## Service Discovery Endpoints

### GET /deployed-services/
**Purpose**: List deployed services for service discovery
**Authentication**: Config token required
**Response**:
```json
[
  {
    "id": 1,
    "deployment_id": 1,
    "config": {
      "domain": "example.com",
      "port": 8080,
      "database": "app_db"
    }
  }
]
```

## WebSocket Endpoint

### WS /deployments/ws/{client_id}
**Purpose**: Real-time deployment updates
**Protocol**: WebSocket
**Authentication**: Send token after connection

**Connection Flow**:
1. Connect to `ws://host/deployments/ws/<uuid>` with a fresh random UUID as client id. A client id
   can only be used by one live connection: connecting with an id that is still connected is refused
   (handshake rejected / close code `1008`) and does not affect the existing connection. The id can
   be reused once its connection is closed.
2. Send authentication message (a **user** access token from `POST /token`):
   ```json
   {"access_token": "<jwt_token>"}
   ```
3. Receive authentication response:
   ```json
   {"type": "authentication", "status": "success"}
   ```
   On failure (invalid or expired token, a service/deployment/config token, or a user that no
   longer exists) the server sends `{"type": "authentication", "status": "failure"}` and closes
   the connection with code `1008`. Reconnect with a new token to try again.
4. Optionally re-authenticate on the same connection by sending a new access token for the
   **same** user; this replaces the session expiry. A token for a different user is rejected and
   closes the connection.
5. Receive real-time events (only authenticated connections receive broadcasts):
   ```json
   {
     "type": "step|deployment|service",
     "id": 1,
     "name": "step_name",
     "state": "success",
     "deployment_id": 1
   }
   ```

## Authentication Summary

| Endpoint | Required Token Type |
|----------|-------------------|
| `POST /token` | None (username/password) |
| `GET /users/me` | User Token |
| `POST /service-token` | User Token |
| `DELETE /service-token/{jti}` | User Token |
| `GET /services/*` | User Token |
| `POST /services/sync` | User Token |
| `DELETE /services/*` | User Token |
| `GET /deployments/` | User Token |
| `POST /deployments/` | Service Token |
| `GET /deployments/{id}` | Service Token |
| `PUT /deployments/finish/` | Deployment Token |
| `POST /steps/` | Deployment Token |
| `GET /steps/` | User Token |
| `GET /deployed-services/` | Config Token |
| `WS /deployments/ws/*` | User Token |

## Error Responses

All endpoints may return these standard error responses:

- **401 Unauthorized**: Invalid or expired token
  ```json
  {"detail": "Could not validate credentials"}
  ```

- **403 Forbidden**: Token lacks required permissions
  ```json
  {"detail": "Wrong service token"}
  ```

- **409 Conflict** (`POST /deployments/`): Another deployment of the service is still running;
  `detail.deployment_id` names it

- **409 Conflict** (`POST /services/sync`): The sync would delete all or more than half of the
  services; `detail.would_delete` lists them. Retry with `force=true` if that is intended

- **404 Not Found**: Resource does not exist
  ```json
  {"detail": "Service not found"}
  ```

- **422 Unprocessable Entity**: Invalid request data
  ```json
  {"detail": [{"loc": ["body", "field"], "msg": "field required"}]}
  ```

- **500 Internal Server Error**: Unexpected system error
  ```json
  {"detail": "Internal server error"}
  ```
