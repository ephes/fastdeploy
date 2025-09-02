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
  "expiration_in_days": 1-180
}
```
**Response**:
```json
{"service_token": "<jwt>", "token_type": "bearer"}
```

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
**Response**:
```json
{"detail": "Services synced"}
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
1. Connect to `ws://host/deployments/ws/<uuid>`
2. Send authentication message:
   ```json
   {"access_token": "<jwt_token>"}
   ```
3. Receive authentication response:
   ```json
   {"type": "authentication", "status": "success"}
   ```
4. Receive real-time events:
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
