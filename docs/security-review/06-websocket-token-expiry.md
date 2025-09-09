# 06 - WebSocket Token Expiry and Authentication UX

## Issue Title
**WebSocket connections are forcibly closed on JWT token expiry without graceful re-authentication mechanism**

## Issue Description

The current WebSocket implementation in fastDeploy abruptly closes connections when JWT tokens expire, resulting in poor user experience and potential loss of real-time deployment monitoring during critical operations.

**Review Feedback**: "WebSocket token expiry UX. Your WS closes on token expiry. The recommendation is to define an {"type":"auth","status":"expiring","exp":"..."} pre-notice and support client re-auth without dropping the socket (or auto-reconnect with backoff)."

## Factual Analysis of Current Implementation

### Server-Side Token Expiry Handling

**File**: `/src/deploy/adapters/websocket.py`

The current implementation demonstrates the problematic behavior:

```python
async def close_on_expire(self, client_id: UUID, expires_at: datetime):
    """
    Schedule closing websocket on token expiration.
    """
    print("close on expire called..")
    message = "Your session has expired."
    now = datetime.now(timezone.utc)
    if now >= expires_at:
        await self.close(client_id, message)
    else:
        # add 5 seconds to avoid closing a reconnecting client
        expires_in_seconds = int((expires_at - now).total_seconds()) + 5
        print("expires in seconds: ", expires_in_seconds)
        loop = asyncio.get_event_loop()
        loop.call_later(expires_in_seconds, asyncio.create_task, self.close(client_id, message))
```

**Lines 34-48**: The `close_on_expire` method schedules a hard connection closure using `loop.call_later()` without providing any advance warning to the client.

**Lines 24-32**: The `close` method sends a single warning message and immediately closes the WebSocket:

```python
async def close(self, client_id: UUID, message: str):
    """
    Close the websocket with a message.
    """
    websocket = self.all_connections.get(client_id)
    if websocket is not None:
        print("closing websocket: ", datetime.now(timezone.utc))
        await websocket.send_json({"type": "warning", "detail": message})
        await websocket.close()
```

### Authentication Flow Analysis

**File**: `/src/deploy/adapters/websocket.py` - Lines 50-68

The authentication process immediately schedules connection closure:

```python
async def authenticate(self, client_id: UUID, access_token: str, uow: AbstractUnitOfWork):
    try:
        user = await user_from_token(access_token, uow)
        token = token_to_payload(access_token)
        expires_at = datetime.fromtimestamp(token["exp"], timezone.utc)
        connection = self.all_connections[client_id]
        # after successful authentication, add connection close callback on token expiration
        await self.close_on_expire(client_id, expires_at)  # ← Immediate scheduling of closure
        # ... rest of authentication
```

**Critical Issue**: The server schedules connection closure immediately upon successful authentication, with no mechanism for graceful re-authentication.

### Client-Side Token Expiry Handling

**File**: `/frontend/src/websocket.ts`

The client-side implementation shows basic reconnection logic but lacks token refresh capabilities:

**Lines 67-103**: `onConnectionClose` method implements basic retry logic:
```typescript
async onConnectionClose(accessToken: string, websocketUrl: string, event: CloseEvent) {
    // ... connection state updates ...
    while (this.retryCount < 3) {
        this.retryCount++;
        await new Promise((resolve) => setTimeout(resolve, 1000));
        console.log("Attempting to reconnect to websocket server: ", this.retryCount);
        if (this.connection.readyState === WebSocket.CLOSED) {
            this.initWebsocketConnection(websocketUrl, accessToken);
            break;
        }
    }
}
```

**Limitations**:
- Uses the same potentially expired `accessToken` for reconnection
- Simple linear retry with 1-second delay (no exponential backoff)
- Limited to 3 reconnection attempts
- No token refresh mechanism

### WebSocket Endpoint Implementation

**File**: `/src/deploy/entrypoints/fastapi_app.py` - Lines 44-60

```python
@app.websocket("/deployments/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: UUID, bus: Bus = Depends()):
    connection_manager = bus.cm
    await connection_manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("access_token") is not None:
                # try to authenticate client
                await connection_manager.authenticate(client_id, data["access_token"], bus.uow)
            # ... rest of message handling
```

**Analysis**: The endpoint supports re-authentication through new `access_token` messages, but the server-side implementation still schedules closure on the initial token expiry.

## UX Impact Assessment

### Critical UX Problems

1. **Abrupt Disconnection**: Users lose real-time deployment monitoring without warning
2. **Poor Timing**: Token expiry (15 minutes default) often occurs during long-running deployments
3. **Silent Failures**: Users may not notice connection loss until checking deployment status
4. **Ineffective Reconnection**: Client retries with expired tokens, leading to authentication failures
5. **No Pre-Warning**: Users receive no advance notice of impending disconnection

### User Journey Analysis

1. **User starts deployment** → WebSocket connects and authenticates
2. **15 minutes pass** → Server schedules connection closure
3. **Token expires** → Server sends warning and closes connection abruptly
4. **Client attempts reconnection** → Uses expired token, fails authentication
5. **Manual intervention required** → User must refresh page or re-login

### Visual UX Impact

**File**: `/frontend/src/components/WebsocketStatus.vue`

The WebSocket status component shows binary online/offline state:
```vue
<div v-if="websocketStore.isOnline" class="websocket online"></div>
<div v-else class="websocket offline"></div>
```

**Problem**: No intermediate state for "expiring soon" or "re-authenticating"

## Current Authentication Token Lifecycle

### Token Creation
**File**: `/src/deploy/auth.py` - Lines 39-54

```python
def create_access_token(payload: dict, expires_delta: timedelta | None = None):
    to_encode = payload.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)  # ← Default 15 minutes
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.token_sign_algorithm)
    return encoded_jwt
```

**Default Expiry**: 15 minutes, which is insufficient for long-running deployments

### Token Validation
**File**: `/src/deploy/auth.py` - Lines 57-68

```python
def token_to_payload(token: str):
    """
    Parse a JWT token and return a dict of its payload.

    The jwt.decode function checks for expiration and raises
    ExpiredSignatureError if it's expired.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.token_sign_algorithm])
```

**Behavior**: Raises `ExpiredSignatureError` on token expiry, handled as authentication failure

## Proposed Re-Authentication Mechanism

### 1. Pre-Expiration Warning System

**Server-Side Enhancement**:
```python
async def schedule_expiry_warning(self, client_id: UUID, expires_at: datetime):
    """
    Send pre-expiration warning to client 5 minutes before token expires.
    """
    now = datetime.now(timezone.utc)
    warning_time = expires_at - timedelta(minutes=5)

    if now < warning_time:
        warning_delay = int((warning_time - now).total_seconds())
        loop = asyncio.get_event_loop()
        loop.call_later(warning_delay, asyncio.create_task,
                       self.send_expiry_warning(client_id, expires_at))

async def send_expiry_warning(self, client_id: UUID, expires_at: datetime):
    """
    Send expiry warning message to client.
    """
    message = {
        "type": "auth",
        "status": "expiring",
        "exp": expires_at.isoformat(),
        "detail": "Your session will expire soon. Please re-authenticate."
    }
    await self.send(client_id, message)
```

### 2. Graceful Re-Authentication Flow

**Modified Authentication Method**:
```python
async def authenticate(self, client_id: UUID, access_token: str, uow: AbstractUnitOfWork):
    try:
        user = await user_from_token(access_token, uow)
        token = token_to_payload(access_token)
        expires_at = datetime.fromtimestamp(token["exp"], timezone.utc)

        # Cancel any existing expiry tasks
        if client_id in self.expiry_tasks:
            self.expiry_tasks[client_id].cancel()

        # Schedule warning instead of immediate closure
        await self.schedule_expiry_warning(client_id, expires_at)

        # Schedule graceful closure (with longer buffer for re-auth)
        await self.schedule_graceful_expiry(client_id, expires_at)

        # ... rest of authentication logic
```

### 3. Token Refresh Integration

**Client-Side Token Refresh**:
```typescript
class WebsocketClient {
    private refreshTokenCallback?: () => Promise<string>;

    setTokenRefreshCallback(callback: () => Promise<string>) {
        this.refreshTokenCallback = callback;
    }

    private async handleExpiryWarning(message: AuthExpiryMessage) {
        if (this.refreshTokenCallback) {
            try {
                const newToken = await this.refreshTokenCallback();
                this.reauthenticate(newToken);
            } catch (error) {
                console.error("Token refresh failed:", error);
                // Fallback to logout
                this.handleAuthFailure();
            }
        }
    }

    private async reauthenticate(newToken: string) {
        if (this.connection?.readyState === WebSocket.OPEN) {
            const credentials = JSON.stringify({ access_token: newToken });
            this.connection.send(credentials);
        }
    }
}
```

## Client-Side Implementation Considerations

### 1. Enhanced Message Handling

**File**: `/frontend/src/websocket.ts` - Enhanced `onMessage` method:

```typescript
onMessage(event: MessageEvent) {
    const message = JSON.parse(event.data) as Message;

    if (message.type === "auth") {
        if (message.status === "expiring") {
            this.handleExpiryWarning(message);
        } else {
            this.onAuthenticationMessage(message as AuthenticationMessage);
        }
    } else {
        this.notifyStores(message);
    }
}
```

### 2. Token Refresh Integration with Auth Store

**File**: `/frontend/src/stores/auth.ts` - Add token refresh method:

```typescript
async refreshToken(): Promise<string> {
    if (!this.accessToken) {
        throw new Error("No active session to refresh");
    }

    // Implement token refresh logic
    const response = await this.client.post<{ access_token: string }>("/token/refresh");
    this.accessToken = response.access_token;
    return response.access_token;
}
```

### 3. Enhanced WebSocket Status Component

**File**: `/frontend/src/components/WebsocketStatus.vue` - Add expiring state:

```vue
<template>
    <div v-if="websocketStore.recentlyReceivedMessage" class="blink_me">&nbsp;</div>
    <div v-if="websocketStore.isOnline" class="websocket online"></div>
    <div v-else-if="websocketStore.isExpiring" class="websocket expiring">⚠️</div>
    <div v-else class="websocket offline"></div>
</template>

<style scoped>
.expiring {
    background-color: orange;
    color: white;
    padding: 5px;
    font-size: 20px;
    animation: pulse 1s ease-in-out infinite alternate;
}

@keyframes pulse {
    from { opacity: 0.6; }
    to { opacity: 1; }
}
</style>
```

## Auto-Reconnect Strategy with Exponential Backoff

### Enhanced Reconnection Logic

```typescript
class WebsocketClient {
    private maxRetries = 10;
    private baseDelay = 1000; // 1 second
    private maxDelay = 30000;  // 30 seconds

    async onConnectionClose(accessToken: string, websocketUrl: string, event: CloseEvent) {
        const websocketStore = useWebsocketStore();
        websocketStore.handling = "on close";
        websocketStore.connection = readyState[this.connection.readyState];
        websocketStore.authentication = "not authenticated";

        await this.reconnectWithBackoff(websocketUrl, accessToken);
    }

    private async reconnectWithBackoff(websocketUrl: string, accessToken: string) {
        let attempt = 0;

        while (attempt < this.maxRetries) {
            attempt++;

            // Exponential backoff with jitter
            const delay = Math.min(
                this.baseDelay * Math.pow(2, attempt - 1) + Math.random() * 1000,
                this.maxDelay
            );

            console.log(`Reconnection attempt ${attempt}/${this.maxRetries} in ${delay}ms`);
            await new Promise(resolve => setTimeout(resolve, delay));

            // Try to refresh token before reconnecting
            try {
                const auth = useAuth();
                if (auth.isAuthenticated) {
                    const freshToken = await auth.refreshToken();
                    accessToken = freshToken;
                }
            } catch (error) {
                console.warn("Token refresh failed, using existing token:", error);
            }

            // Attempt reconnection
            if (this.connection?.readyState === WebSocket.CLOSED) {
                try {
                    this.initWebsocketConnection(websocketUrl, accessToken);
                    // Wait for connection result
                    await this.waitForConnectionResult();

                    if (this.connection?.readyState === WebSocket.OPEN) {
                        console.log("Reconnection successful");
                        this.retryCount = 0;
                        return;
                    }
                } catch (error) {
                    console.error(`Reconnection attempt ${attempt} failed:`, error);
                }
            }
        }

        console.error("Max reconnection attempts reached. Giving up.");
        // Redirect to login or show error notification
        const auth = useAuth();
        auth.logout();
    }

    private async waitForConnectionResult(timeout = 5000): Promise<void> {
        return new Promise((resolve, reject) => {
            const startTime = Date.now();
            const checkConnection = () => {
                if (this.connection?.readyState === WebSocket.OPEN) {
                    resolve();
                } else if (Date.now() - startTime > timeout) {
                    reject(new Error("Connection timeout"));
                } else {
                    setTimeout(checkConnection, 100);
                }
            };
            checkConnection();
        });
    }
}
```

## Recommendations

### Priority 1: Critical UX Fixes

1. **Implement Pre-Expiration Warning System**
   - Send warning 5 minutes before token expires
   - Include exact expiration timestamp
   - Use standardized message format: `{"type":"auth","status":"expiring","exp":"..."}`

2. **Add Graceful Re-Authentication Support**
   - Modify server to accept new tokens without closing connection
   - Extend grace period after token expiry (2-3 minutes) for re-authentication
   - Cancel existing expiry timers when new valid token received

### Priority 2: Enhanced Client-Side Handling

3. **Implement Exponential Backoff Reconnection**
   - Replace linear retry with exponential backoff
   - Add jitter to prevent thundering herd
   - Increase max retry attempts to 10 with 30-second max delay

4. **Add Token Refresh Mechanism**
   - Integrate automatic token refresh on expiry warnings
   - Fallback to logout only after refresh attempts fail
   - Store fresh tokens securely for reconnection attempts

### Priority 3: UX Enhancements

5. **Enhance WebSocket Status Indicators**
   - Add "expiring soon" visual state (orange indicator)
   - Show countdown timer for token expiry
   - Display reconnection attempt status

6. **Increase Default Token Lifetime**
   - Consider extending default token expiry to 60 minutes for deployment use cases
   - Implement sliding session extension for active users
   - Add configurable token lifetime per use case

### Implementation Timeline

- **Week 1**: Implement pre-expiration warnings and graceful re-auth on server
- **Week 2**: Add client-side token refresh and enhanced reconnection logic
- **Week 3**: Update UI components and status indicators
- **Week 4**: Testing, monitoring, and deployment

### Testing Requirements

1. **Unit Tests**: Token expiry scenarios, reconnection logic
2. **Integration Tests**: End-to-end WebSocket authentication flows
3. **Load Tests**: Multiple concurrent connections with token refresh
4. **Manual Tests**: User experience during long-running deployments

## Conclusion

The current WebSocket token expiry implementation creates a poor user experience by abruptly disconnecting users without warning or graceful recovery options. The proposed solution provides a comprehensive approach to graceful session management while maintaining security through proper token lifecycle management.

**Key Benefits**:
- Eliminates unexpected disconnections during critical deployments
- Provides advance warning for token expiry
- Enables seamless token refresh without connection loss
- Implements robust reconnection with exponential backoff
- Maintains security through proper token validation

**Security Considerations**:
- Pre-expiration warnings do not expose sensitive token data
- Grace period for re-authentication is limited to prevent abuse
- Failed refresh attempts trigger proper logout flows
- All token operations maintain existing validation requirements
