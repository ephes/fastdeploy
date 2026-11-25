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
  `LOGIN_FAILURE_WINDOW_SECONDS` (default 900) from the recorded failure. Pending password checks
  count while they run. While limited, the password is not checked, so the right
  password is refused as well. A successful login clears the count of that user name and address. Tokens
  that were already issued keep working.

### POST /service-token
**Purpose**: Generate service token for deployments
**Authentication**: User token for a user listed in `SERVICE_TOKEN_ADMIN_USERS`; otherwise **403**
**Request Body**:
```json
{
  "service": "<service_name>",
  "origin": "<origin_identifier>",
  "expiration_in_days": 1
}
```
`expiration_in_days` defaults to 1 when omitted. When supplied, it must be a JSON integer from 1
to `SERVICE_TOKEN_MAX_EXPIRE_DAYS` (default 90). Booleans, strings and floating-point values
return **422** before issuance.
The service and current user must exist and `origin` must contain non-whitespace text,
as in CLI issuance. Invalid issuance returns **422** without recording a token.
With a valid request body, non-admins are refused with **403** before the issuance rules are applied.
The token is recorded with its id (`jti`) so it can be revoked.

**Response**:
```json
{"service_token": "<jwt>", "token_type": "bearer", "jti": "<token id>", "expires_at": "<datetime>"}
```

### DELETE /service-token/{jti}
**Purpose**: Revoke a service token. Deployments can no longer be started with it
**Authentication**: Administrator user token (`SERVICE_TOKEN_ADMIN_USERS`) required
**Response** (revoking an already revoked token succeeds again and keeps the first time):
```json
{"detail": "Service token <jti> revoked", "jti": "<jti>", "revoked_at": "<datetime>"}
```
**403 Forbidden**: current user is not an allowlisted administrator; checked before looking up the id

Administrators receive **404 Not Found** when the ID is unknown or cannot fit
the stored identifier format. IDs must contain 1–64 characters without NUL.
An ID outside these limits is rejected before the token lookup.

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
A services directory that cannot be listed, or that exceeds the source admission limits
(4,096 root entries or 1,000 service directories), is refused with **422** and a short
`detail` message, the same way `POST /services/sync` refuses it.

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

All additions, edits and deletions in a sync commit together. A database failure
rolls back service changes and history cascades, and publishes no success events;
a later request can retry the entire sync.

The web frontend shows the deletion-count refusal and offers **force sync** after
a 409 response with a nonblank message, a positive safe integer total, and unique
nonempty service names accounting for more than half and at most all of that total.
Other conflicts show generic sync failure feedback. The force button retries with
`force=true` after a confirmation dialog.
Only the latest sync attempt in the current login session owns its success/refusal/error
feedback. Starting another attempt retires earlier responses even if they finish later;
it does not cancel or undo server-side work. Force confirmation remains required.

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

Integer service IDs outside 1–2,147,483,647 return **404 Not Found** before the
delete is dispatched. Missing services within that range return the same response.

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

The web frontend shows a deletion error only for the latest attempt on that
service in the current login session. An HTTP confirmation or WebSocket deletion
clears the row and its error and prevents an in-flight refresh from restoring it.

## Deployment Endpoints

### POST /deployments/
**Purpose**: Initiate new deployment
**Authentication**: Service token required; only its registered service can run

Echoport restores (`env.ECHOPORT_ACTION="restore"`) and any supplied `env.ECHOPORT_KEY` require
a configured `RESTORE_POLICIES` entry for that service, an explicit matching `ECHOPORT_BUCKET`,
and a relative `ECHOPORT_KEY` below one of its allowed prefixes. Missing or invalid restore input returns
**422** and starts nothing. See [restore policy](auth.md#restore-input-policy).

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
are reclassified after their deployment rows are locked, using the current time and steps.
Rows that are still orphaned are finished as failed as part of a successful start. A row that
has become active blocks the start, and a rejected (409) start changes nothing. Other unfinished
deployments that have reached the deployment token lifetime
(`DEPLOYMENT_ACCESS_TOKEN_EXPIRE_MINUTES`, default 480) are left untouched and allow the new start,
even when a step has appeared since the first check. Concurrent starts for the same service are
serialized by a database row lock on the service, so exactly one of them succeeds.

Admission flush, planned-step insertion or commit failures roll back the entire
admission and do not launch a task or publish a deployment start.

**Start order**: the service definition is loaded after taking the service row lock.
Planning and launch use that snapshot, so a service sync committed before the lock
is acquired supplies the current script and configuration. The lock stays held
through admission. When reusing a previous successful deployment's step names,
the latest recorded start wins. Deployments without a recorded start sort last.
For equal timestamps or multiple missing start times, the highest deployment ID
wins. The deployment and its planned steps are committed in one transaction before the
detached deploy task is started, so a task that reports its first step immediately finds the planned
steps. If the deploy task cannot be started, the deployment is finished as failed at once: its planned
steps are removed and a step named `deployment launch failed` with state `failure` records the error
type. After this result is committed, fastDeploy attempts to log the details. If logging fails,
the request still returns **500** with the failed deployment id and the service is free for the next start:
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
On reads, the final inactivity check uses the time after both locks are held and the current
steps have been loaded. Step activity reported during the wait counts toward the inactivity
window. The cleanup warning is best effort and emitted after the failure result is committed.

### GET /deployments/
**Purpose**: List a bounded history page; reconcile at most 50 oldest eligible
orphaned deployments first. One candidate query filters unfinished deployments
using all step activity and open states before applying the batch limit, without
loading the full unfinished history or querying activity once per deployment.
For each candidate, cleanup reads only the owning service ID before locking the
service and then the deployment. It loads the current steps under those locks
to recheck eligibility and skips deployments deleted in the meantime.
Repeated history requests drain a stable eligible backlog; recent/running rows do
not block older candidates. The returned history page keeps its requested size,
order and cursor regardless of the maintenance batch. Detail reads still reconcile
only their authorized deployment.
Completed history is excluded from the orphan scan.

**Query parameters** (additive; the response remains a JSON array):
- `limit`: 1–200, default **50**.
- `before_id`: exclusive deployment id cursor (1–2147483647); return ids strictly below it.
- `service_id`: optional service filter (1–2147483647). An unknown service returns `[]`.

Out-of-range identifiers return HTTP 422.

Rows are ordered by **descending id**. Pass the last row's id as `before_id` for
subsequent pages, retaining the same service filter. An empty page ends history;
a short page also means no more rows at that time. A full final page may be followed
by an empty one. New inserts appear on refresh without shifting older pages;
this is cursor traversal, not a database snapshot.

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

The web UI keeps newer websocket updates and deletions when an older in-flight list
response arrives. Logging out also invalidates pending list responses.

The web UI initially loads 50 rows and offers **Load more**. Switching services
starts a fresh history page. Events remain live during paging and logout discards
pending pages. API consumers that previously expected the full history must now
iterate pages; CLI deployment operations do not consume this history endpoint.

### GET /deployments/{deployment_id}
**Purpose**: Get deployment details with steps
**Authentication**: Service token required (must match deployment's service)
**Errors**: `404 {"detail": "Deployment not found"}` for an unknown id, an integer id outside
1–2147483647, or a deployment of another service. Out-of-range ids are rejected before the
deployment lookup. The 404 is preserved if diagnostic logging fails. An orphaned unfinished deployment
(see [Orphaned deployments](#orphaned-deployments)) is finished as failed on read, but only after the
ownership check. The endpoint uses the deployment and steps already loaded for the response to
identify candidates. Reconciliation rechecks under locks, and the endpoint reloads the detail
after a successful update.
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

Finishing and step reporting serialize on the deployment row. If the final report
commits first, finishing preserves it and removes remaining open steps. If finishing
commits first, a later report is refused because the deployment has finished; it
cannot recreate removed steps. Repeated finishing preserves the original finish
time and publishes no second completion event.

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
separate steps. Other processing failures return **400** with
`{"detail": "Something went wrong"}`. The route logs the deployment ID and exception class name
(up to 100 characters) for these failures, omitting exception text and tracebacks.
Both error responses are preserved if the diagnostic log fails.

### GET /steps/
**Purpose**: List a bounded step page for a deployment
**Authentication**: User token required
**Query Parameters**: `deployment_id` (required, 1–2147483647), `limit` (1–25, default 25),
`before_id` (optional exclusive cursor, 1–2147483647). Out-of-range identifiers return HTTP 422.

Rows are ordered by descending immutable step id. Pass the last id as `before_id`
for the next page. A short page, including an empty page after an exactly full final
page, explicitly completes the inventory at that traversal. Inserts with higher ids
arrive through WebSocket or a fresh traversal; updates/deletions can happen during
paging, so this is not a frozen database snapshot. The response remains an array,
but consumers that previously expected all rows must now traverse pages.
Each page reads the deployment and at most 25 step rows in a single SQL statement.
An existing deployment with no matching steps returns an empty array. Even maximally escaped persisted
name/message fields keep each response below the frontend's 1 MiB body limit.
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

Rows are ordered by descending deployed-service ID. Omitting both query
parameters returns the full inventory as a JSON array.

- `limit`: 1–200 rows. Start a paged read with, for example, `?limit=50`.
- `before_id`: exclusive cursor (1–2147483647). Pass the last row's `id`
  and repeat the same `limit`. A request with only `before_id` returns at
  most 50 rows.

Use the deployed-service `id` for the cursor. Multiple rows can share a
`deployment_id`. A short or empty page means the inventory is exhausted at
the time of the read. Newer rows appear when traversal starts again.

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
   be reused once its connection is closed. Each process holds at most `WEBSOCKET_MAX_CONNECTIONS`
   (default 256) connections, of which at most `WEBSOCKET_MAX_UNAUTHENTICATED_CONNECTIONS`
   (default 32) have not authenticated yet, and at most
   `WEBSOCKET_MAX_UNAUTHENTICATED_PER_ADDRESS` (default 4) of those from one client address
   (after trusted proxy headers). Further handshakes are rejected (HTTP 403 from the server;
   ASGI test clients see close code `1013`); retry later. A connection that authenticates or
   ends frees its slot.
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
   If the token expires during verification, the server follows the same failure path
   before registering the socket as authenticated or scheduling its expiry.
   The first authentication has to succeed within `WEBSOCKET_AUTH_TIMEOUT_SECONDS` (default 10)
   after the connection was accepted, whatever else the client sends in the meantime. A connection
   that is still not authenticated then is closed with code `1008` and the close reason
   `authentication timeout`; no message is sent before the close. Connect again and send the token
   right away.
   Every client frame, before and after authentication, must be a text frame of at most
   8 KiB (UTF-8) holding one JSON object without duplicate member names; an `access_token`
   member must be a nonempty string of at most 4,096 characters. Any other frame closes the
   connection before credential work: `1009` (`control message too large`) for an oversized
   frame, otherwise `1008` (`text frames only` or `invalid control message`). The server
   receives a whole frame before this check, up to Uvicorn's `--ws-max-size` (16 MiB by
   default); deployments can lower that option to bound per-frame memory as well.
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

Sends on each connection are serialized with an asyncio lock: broadcasts and
authentication/control responses cannot overlap. The send deadline includes time
waiting for that lock. Failed or cancelled transport sends retire their queue before
releasing the lock, including queued final control frames. Disconnect discards queued frames for that socket; a reused
client id gets independent send ownership. Other clients keep independent queues.

FastAPI lifespan shutdown stops connection admission, forgets current sockets,
closes them concurrently and drains only this manager's close and expiry tasks.
The drain gets two seconds before remaining tasks are cancelled and awaited.
A subsequent lifespan starts with empty connection state. Late request teardown
uses a bounded close without creating detached tasks after shutdown.

Slow clients: every event is sent to all authenticated connections at the same time, and each
connection has 5 seconds to take it. A connection that does not (for example a suspended browser
tab with a full receive buffer) is closed with code `1013` and forgotten, so it can delay neither
the other clients nor the request that produced the event. Events are not queued for it: reconnect,
authenticate again and reload the current state over the REST endpoints.
Ordinary transport send errors also forget and close that connection with code `1013`,
without waiting for a receive-side disconnect. This removes its principal and expiry
timer and preserves healthy peers and any newer connection using the same client id.
The caller waits at most 1 second for transport close.
Refused handshakes and failed broadcast sends are closed before diagnostics are logged.
A logging handler failure cannot prevent this cleanup or propagate to the broadcaster.

Control messages (authentication success/failure and expiry warnings) also have a 5-second
send budget. All control and endpoint-cleanup callers wait at most 1 second for a close,
including duplicate-id refusal. Cleanup removes connection state and cancels expiry callbacks
even if the peer stops reading. A close that outlasts this wait continues in the background
under the ASGI server's transport-close deadline, allowing its TCP teardown to finish;
cleanup for an old socket never removes a replacement
using the same client id. A timed-out authentication-success send closes with code `1013`.

Event publication diagnostics at INFO contain only the event class and its `id`, `service_id` and
`deployment_id` when present. Event payloads (including context, configuration, names and messages)
are omitted from these logs and the publisher emits no stdout output. Authorized websocket delivery
keeps the full event payload. Enable INFO logging to see these diagnostics. Message-bus DEBUG and
handler failure logs also include only the message class and these identifiers (absent ids are
`None`), without message or handler reprs. Message-bus failures add the exception
class (at most 100 characters), without exception text, SQL parameters or tracebacks.
Command exceptions still propagate; failed event handlers remain isolated so later
handlers run. Deployed-service insertion emits no stdout output.

## Authentication Summary

| Endpoint | Required Token Type |
|----------|-------------------|
| `POST /token` | None (username/password) |
| `GET /users/me` | User Token |
| `POST /service-token` | Administrator user token (`SERVICE_TOKEN_ADMIN_USERS`) |
| `DELETE /service-token/{jti}` | Administrator user token (`SERVICE_TOKEN_ADMIN_USERS`) |
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

### Mutation failures

Service deletion and deployment finish return 404 only for an established missing
record. Deployment starts retain validation (413/422) and active-deployment (409)
responses; a missing service at the initial start lookup is 404. A concurrent
deletion after that lookup can instead fail the transaction with 500. Unexpected database, commit
or storage failures return a generic 500, never backend exception details. A 500
is not confirmation that the mutation succeeded: inspect deployment history before
retrying a start, since a response can be lost after a commit.


### Report timestamp admission

Step reports require `started` with an explicit timezone offset. The API accepts
at most five minutes of future clock skew, normalizes accepted starts to UTC,
and refuses naive or later timestamps with 422 before creating steps or events.
The domain boundary applies the same rule to supplied start times. Correct the
runner clock/offset before retrying; timestamps are never silently repaired.
Persisted `finished` times remain server-owned. Offset-equivalent starts identify
the same report, so valid retries remain idempotent. The skew allowance does not
replace server finish times or the activity/reconciliation clock.

## Mutation body admission

Before JSON/form parsing, credential dependencies or database work, all HTTP
`POST`, `PUT`, `PATCH` and `DELETE` requests have a 1 MiB actual-body limit and a
single 10-second receive deadline. This includes login, deployment start and
step reporting. An oversized body returns 413; a slow/incomplete body returns
408. Content-Length can only cause early refusal: chunked input and incorrect
lengths still undergo actual-byte admission. Empty and ordinary bodies continue
to their normal route validation. Disconnected callers cause no route execution.
The deployment context's configured JSON limit still applies within this outer
HTTP envelope; increasing it cannot bypass the 1 MiB body limit.
