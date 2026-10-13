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
**Errors**:
- `401` for a wrong user name or password. Both take the same time: the password hash check also runs
  for unknown users.
- `429` with a `Retry-After` header (seconds) and `{"detail": "Too many failed login attempts"}` after
  too many failed attempts: `LOGIN_FAILURE_LIMIT` (default 10) for one user name from one client address,
  or `LOGIN_ADDRESS_FAILURE_LIMIT` (default 50) from one client address for any user names, inside
  `LOGIN_FAILURE_WINDOW_SECONDS` (default 900). While limited, the password is not checked, so the right
  password is refused as well. A successful login clears the count of that user name and address. Tokens
  that were already issued keep working.

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
**Purpose**: Remove service from database, together with its deployments and their steps
**Authentication**: User token required
**Response**:
```json
{"detail": "Service 1 deleted"}
```

A service with a running deployment is not deleted. The request is rejected with **409 Conflict**
and nothing changes, because the detached deploy task would keep running without its deployment
record:
```json
{
  "detail": {
    "message": "Deployment 41 is still running for service 1",
    "deployment_id": 41
  }
}
```
"Running" follows the same rule as the single-flight check of `POST /deployments/` and the services
sync: orphaned deployments and deployments older than the deployment token lifetime do not block.
The check takes the same service lock as a deployment start, so a delete that races with a start
waits for it and is then refused. Retry after the deployment has finished.

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
The context is stored with the deployment, passed to the deploy script and sent to every websocket
client. Its JSON encoding may be at most `DEPLOYMENT_CONTEXT_MAX_BYTES` bytes (default 65536, counted
in UTF-8); a larger context is rejected with **413** and no deployment is started:
```json
{"detail": "Deployment context is too large: 70000 bytes, at most 65536 are allowed"}
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
Orphaned unfinished deployments of the service (see [Orphaned deployments](#orphaned-deployments))
do not block: they are finished as failed as part of a successful start, so a stale row cannot wedge
the service. A rejected (409) start changes nothing. Unfinished deployments started longer ago than the deployment token
lifetime (`DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`, default 480) can no longer report or finish
and do not block new deployments either. Concurrent starts for the same service are serialized
by a database row lock on the service, so exactly one of them succeeds.

**Start order**: the deployment and its planned steps are committed in one transaction before the
detached deploy task is started, so a task that reports its first step immediately finds the planned
steps. If the deploy task cannot be started, the deployment is finished as failed at once: its planned
steps are removed and a step named `deployment launch failed` with state `failure` records the error
type (details are in the fastdeploy service log). The request is answered with **500** and the failed
deployment id, and the service is free for the next start:
```json
{
  "detail": {
    "message": "Deploy task of deployment 42 could not be started",
    "deployment_id": 42
  }
}
```
The failed deployment is returned by `GET /deployments/` and `GET /deployments/{deployment_id}`; no
websocket events are broadcast for it.

### Orphaned deployments
A deployment is orphaned when it is unfinished, has no running or pending steps, and neither the
deployment start nor any step start/finish happened within `DEPLOYMENT_ORPHAN_RECONCILE_DELAY_SECONDS`
(default 300). Its deploy task stopped reporting without finishing it (for example because the API
was unreachable when the deploy failed), so its outcome is unknown. Orphaned deployments are never
recorded as successful: `GET /deployments/`, `GET /deployments/{deployment_id}` and a successful
`POST /deployments/` for the same service finish them and add a step named `deployment orphaned`
with state `failure` whose `message` records the reason. The step is returned with the other steps
(`GET /deployments/{deployment_id}`, `GET /steps/?deployment_id=`), broadcast over the websocket, and
shown as a failed step in the web frontend. A later `PUT /deployments/finish/` from the deploy task
does not change the result. The cleanup, `PUT /deployments/finish/` and `POST /steps/` lock the deployment
row, so a deploy task that finishes or reports a step at the same time is never marked as orphaned.

### GET /deployments/
**Purpose**: List all deployments; orphaned deployments are finished as failed first
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
**Errors**: `404 {"detail": "Deployment not found"}` both for an unknown id and for a deployment of
another service, so the response does not reveal which ids exist. An orphaned unfinished deployment
(see [Orphaned deployments](#orphaned-deployments)) is finished as failed on read, but only after the
ownership check.
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
**Purpose**: Report the progress or the result of a step
**Authentication**: Deployment token required
**Request Body**:
```json
{
  "name": "step_name",
  "state": "running|success|failure",
  "started": "2026-10-13T10:00:00Z",
  "finished": "2026-10-13T10:01:00Z",
  "message": "Status message or failure details; may be empty"
}
```
**Response**:
```json
{"detail": "step processed"}
```

`message` is required and may be an empty string. The accepted report states are `running` (the step
has started; a progress report), `success` and `failure` (its result). `pending` and unknown states are
rejected with **422** before any step changes or events; `pending` is the state of a planned step and
is never reported. Direct domain processing rejects them with `ValueError` before mutation.

A `running` report marks its step as running and updates its message; it never advances another
planned step and never changes a step that already has a result. Only steps that are pending or
running are looked up by name, so a `running` report that arrives after the result of a step of the
same name is stored as a separate step, and the result stays as reported. A `success` result moves the
next planned step to `running`.

Size limits: `name` may have at most 255 characters and `message` at most 4096 (the
sizes of the database columns). A longer value is rejected with **422** and the usual validation
error body, which names the field (`"loc": ["body", "message"]`, `"type": "string_too_long"`); the step
is not stored. The deploy task cuts messages to 4096 characters before it reports them.

Reporting a step is idempotent, so the deploy task can safely repeat a report whose response was lost. A
report is identified by its `name` and `started` timestamp (a `started` without a timezone counts as
server local time): sending the same result again (same `state` and `message`) changes nothing, adds no step, broadcasts no event and gets the same response. The same
`name` and `started` with a different `state` or `message` is rejected with **409 Conflict**, so a
progress report and the result of a step need different `started` timestamps (the deploy task stamps
every script line with its own). Steps that share a name but have different `started` timestamps are
separate steps.

### GET /steps/
**Purpose**: List steps for a deployment
**Authentication**: User token required
**Query Parameters**: `?deployment_id=1`
**Errors**: `404 {"detail": "Deployment not found"}` for an unknown deployment id
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
   The first authentication has to succeed within `WEBSOCKET_AUTH_TIMEOUT_SECONDS` (default 10)
   after the connection was accepted, whatever else the client sends in the meantime. A connection
   that is still not authenticated then is closed with code `1008` and the close reason
   `authentication timeout`; no message is sent before the close. Connect again and send the token
   right away.
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

Slow clients: every event is sent to all authenticated connections at the same time, and each
connection has 5 seconds to take it. A connection that does not (for example a suspended browser
tab with a full receive buffer) is closed with code `1013` and forgotten, so it can delay neither
the other clients nor the request that produced the event. Events are not queued for it: reconnect,
authenticate again and reload the current state over the REST endpoints.

Event publication diagnostics at INFO contain only the event class and its `id`, `service_id` and
`deployment_id` when present. Event payloads (including context, configuration, names and messages)
are omitted from these logs and the publisher emits no stdout output. Authorized websocket delivery
keeps the full event payload. Enable INFO logging to see these diagnostics. This contract covers
these two publisher INFO calls only; message-bus DEBUG and failure logs can still contain payloads.

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

- **409 Conflict** (`POST /deployments/`): Another deployment of the service is still running;
  `detail.deployment_id` names it

- **413 Content Too Large** (`POST /deployments/`): The JSON encoded context is larger than
  `DEPLOYMENT_CONTEXT_MAX_BYTES`; no deployment was started

- **422 Unprocessable Content** (`POST /steps/`): `name` or `message` is longer than allowed, or `state` is not `running`, `success` or `failure`
  (`name`: 255 characters; `message`: 4096 characters)

- **500 Internal Server Error** (`POST /deployments/`): The deploy task could not be started; the
  deployment `detail.deployment_id` was finished as failed

- **409 Conflict** (`POST /steps/`): The step (same `name` and `started`) was already reported with a
  different `state` or `message`

- **409 Conflict** (`DELETE /services/{service_id}`): The service has a running deployment and was
  not deleted; `detail.deployment_id` names it

- **409 Conflict** (`POST /services/sync`): The sync would delete all or more than half of the
  services; `detail.would_delete` lists them. Retry with `force=true` if that is intended

- **404 Not Found**: Resource does not exist, or (`GET /deployments/{deployment_id}`) belongs to
  another service
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
