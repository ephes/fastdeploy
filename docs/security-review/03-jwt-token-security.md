# Security Issue: JWT Token Algorithm & Key Management

## Issue Description

**Security Concern**: The current JWT implementation uses HMAC-SHA256 (HS256) symmetric signing with a single environment-based secret key. This design creates a security vulnerability where every token verifier implicitly becomes a full token signer, violating the principle of least privilege.

**Reported Issue**: "Token algorithm & key management. Spec §2.2 mandates HS256 with a single env key. That makes every token verifier implicitly a full signer. The recommendation is to switch to asymmetric signing (RS256 or EdDSA/Ed25519) with JWKS + kid for rotation; add aud, nbf, jti (revocation)."

## Factual Analysis

### Current Implementation Assessment

The security concern is **factually correct**. The current JWT implementation exhibits the following characteristics:

#### 1. Symmetric Key Algorithm (HS256)
**Location**: `/Users/jochen/projects/fastdeploy/src/deploy/config.py:16`
```python
token_sign_algorithm: str = "HS256"
```

**Location**: `/Users/jochen/projects/fastdeploy/src/deploy/auth.py:53,64-68`
```python
# Token creation
encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.token_sign_algorithm)

# Token verification
return jwt.decode(
    token,
    settings.secret_key,
    algorithms=[settings.token_sign_algorithm],
)
```

#### 2. Single Secret Key Management
**Location**: `/Users/jochen/projects/fastdeploy/src/deploy/config.py:20`
```python
secret_key: str = Field(...)  # Required from environment
```

**Location**: `/Users/jochen/projects/fastdeploy/ansible/env.template.j2:1`
```
SECRET_KEY={{ fastdeploy_secret_key }}
```

#### 3. Missing JWT Security Claims
Analysis of current token payloads shows absence of recommended JWT security claims:

**User Token Payload** (`/Users/jochen/projects/fastdeploy/src/deploy/entrypoints/routers/users.py:44-46`):
```python
payload={"user": user.name, "type": "user"}  # Missing: aud, nbf, jti
```

**Service Token Payload** (`/Users/jochen/projects/fastdeploy/src/deploy/entrypoints/routers/users.py:59-64`):
```python
payload = {
    "type": "service",
    "service": service_in.service,
    "origin": service_in.origin,
    "user": user.name,
}  # Missing: aud, nbf, jti
```

**Deployment Token Payload** (`/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:36-40`):
```python
payload = {
    "type": "deployment",
    "deployment": deployment.id,
}  # Missing: aud, nbf, jti
```

#### 4. JWT Library Capabilities
**Location**: `/Users/jochen/projects/fastdeploy/pyproject.toml:20`
```toml
"python-jose[cryptography]>=3.3.0"
```

The `python-jose[cryptography]` library supports:
- ✅ RS256 (RSA-SHA256) asymmetric signing
- ✅ EdDSA/Ed25519 asymmetric signing
- ✅ JWKS (JSON Web Key Sets)
- ✅ Standard JWT claims (aud, nbf, jti, iss, sub)

## Security Impact Assessment

### Current Vulnerabilities

1. **Token Forgery Risk**: Any component that can verify JWT tokens can also create valid tokens
   - **Impact**: HIGH - Complete authentication bypass possible
   - **Affected Components**: All services with access to `SECRET_KEY`

2. **Key Compromise Amplification**: Single key compromise affects entire system
   - **Impact**: CRITICAL - Total system compromise from single secret exposure
   - **Risk Vectors**: Environment variable exposure, log files, process dumps

3. **No Token Revocation**: Missing `jti` (JWT ID) prevents individual token invalidation
   - **Impact**: MEDIUM - Cannot revoke specific compromised tokens
   - **Business Impact**: Must revoke all tokens system-wide

4. **Audience Validation Missing**: No `aud` claim validation allows token misuse
   - **Impact**: MEDIUM - Tokens intended for one service accepted by another
   - **Example**: Service token used as user token in different context

5. **No "Not Before" Protection**: Missing `nbf` allows immediate token use
   - **Impact**: LOW - Cannot implement delayed token activation
   - **Use Case**: Prevents pre-generated token abuse

## Current JWT Implementation Details

### Token Creation Functions
- **Location**: `/Users/jochen/projects/fastdeploy/src/deploy/auth.py:39-54`
- **Algorithm**: HS256 (symmetric)
- **Key Source**: Environment variable `SECRET_KEY`
- **Claims**: Only `exp` (expiration) + custom claims

### Token Verification Functions
- **Location**: `/Users/jochen/projects/fastdeploy/src/deploy/auth.py:57-68`
- **Verification**: Signature + expiration only
- **Missing Validations**: audience, not-before, issuer, JWT ID

### Token Usage Points
1. **User Authentication**: `/Users/jochen/projects/fastdeploy/src/deploy/entrypoints/routers/users.py:32-47`
2. **Service Tokens**: `/Users/jochen/projects/fastdeploy/src/deploy/entrypoints/routers/users.py:56-67`
3. **Deployment Tokens**: `/Users/jochen/projects/fastdeploy/src/deploy/tasks.py:35-40`
4. **WebSocket Authentication**: `/Users/jochen/projects/fastdeploy/src/deploy/adapters/websocket.py`

## Proposed Asymmetric Signing Implementation

### 1. Algorithm Migration Strategy

**Phase 1: Dual Algorithm Support**
```python
# config.py additions
token_sign_algorithm: str = "RS256"  # Change default
legacy_token_sign_algorithm: str = "HS256"  # Support existing tokens
private_key_path: str = Field(...)  # RSA private key file
public_key_path: str = Field(...)   # RSA public key file
jwks_endpoint: str = "/api/v1/.well-known/jwks.json"  # JWKS discovery
```

**Phase 2: Enhanced Token Creation**
```python
def create_access_token_v2(
    payload: dict,
    expires_delta: timedelta | None = None,
    audience: str | None = None,
    not_before: datetime | None = None,
    jwt_id: str | None = None
) -> str:
    """Create JWT with enhanced security claims."""
    to_encode = payload.copy()

    # Standard claims
    now = datetime.now(timezone.utc)
    to_encode.update({
        "exp": now + (expires_delta or timedelta(minutes=15)),
        "iat": now,  # Issued at
        "iss": "fastdeploy",  # Issuer
        "nbf": not_before or now,  # Not before
        "jti": jwt_id or str(uuid.uuid4()),  # JWT ID for revocation
    })

    if audience:
        to_encode["aud"] = audience  # Audience

    # Use RSA private key for signing
    private_key = load_private_key()
    return jwt.encode(to_encode, private_key, algorithm="RS256")
```

### 2. JWKS Implementation

**JWKS Endpoint** (new file: `/Users/jochen/projects/fastdeploy/src/deploy/entrypoints/routers/jwks.py`):
```python
@router.get("/.well-known/jwks.json")
async def get_jwks():
    """Return JSON Web Key Set for token verification."""
    public_key = load_public_key()

    # Convert RSA public key to JWKS format
    numbers = public_key.public_numbers()

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": get_key_id(),  # Key identifier for rotation
                "n": base64url_encode(numbers.n.to_bytes(...)),
                "e": base64url_encode(numbers.e.to_bytes(...)),
                "alg": "RS256",
            }
        ]
    }
```

### 3. Token Revocation System

**Database Schema Addition**:
```python
# In orm.py
class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti = Column(String, primary_key=True)  # JWT ID
    revoked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # Original token expiry
    reason = Column(String)  # Revocation reason
```

**Revocation Check**:
```python
def is_token_revoked(jwt_id: str) -> bool:
    """Check if token is in revocation list."""
    # Query database for revoked JTI
    return jwt_id in revoked_tokens_cache
```

### 4. Enhanced Token Validation

```python
def token_to_payload_v2(token: str, expected_audience: str | None = None):
    """Parse JWT with comprehensive validation."""
    try:
        public_key = load_public_key()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer="fastdeploy",
            # Automatically validates exp, nbf, iat
        )

        # Check revocation
        jwt_id = payload.get("jti")
        if jwt_id and is_token_revoked(jwt_id):
            raise ValueError("Token has been revoked")

        return payload

    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except InvalidAudienceError:
        raise ValueError("Invalid token audience")
    except InvalidSignatureError:
        raise ValueError("Invalid token signature")
```

## Migration Strategy and Backward Compatibility

### Phase 1: Preparation (1-2 weeks)
1. **Generate RSA Key Pair**:
   ```bash
   # Generate 2048-bit RSA private key
   openssl genpkey -algorithm RSA -out fastdeploy_private.pem -pkcs8 -pass pass:$PASSPHRASE

   # Extract public key
   openssl rsa -pubout -in fastdeploy_private.pem -out fastdeploy_public.pem -passin pass:$PASSPHRASE
   ```

2. **Add Configuration Support**:
   - Add RSA key paths to `config.py`
   - Implement key loading utilities
   - Add JWKS endpoint

3. **Database Migration**:
   - Create `revoked_tokens` table
   - Add JWT ID tracking

### Phase 2: Dual Algorithm Support (2-3 weeks)
1. **Implement V2 Token Functions**:
   - `create_access_token_v2()` with RS256
   - `token_to_payload_v2()` with enhanced validation
   - Keep existing functions for backward compatibility

2. **Gradual Migration**:
   - New tokens use RS256 + enhanced claims
   - Existing HS256 tokens remain valid during transition
   - Token verification supports both algorithms

3. **Enhanced Security Claims**:
   - Add `aud` validation per token type:
     - User tokens: `aud=["fastdeploy:api"]`
     - Service tokens: `aud=["fastdeploy:deployment"]`
     - Deployment tokens: `aud=["fastdeploy:steps"]`
   - Add `jti` for all new tokens
   - Implement `nbf` for service tokens (prevent immediate use)

### Phase 3: Migration Completion (1-2 weeks)
1. **Phase Out HS256**:
   - Stop creating new HS256 tokens
   - Set deprecation timeline (e.g., 30 days)
   - Log warnings for HS256 token usage

2. **Remove Legacy Support**:
   - Remove HS256 verification after deprecation period
   - Update documentation
   - Remove `secret_key` configuration

### Phase 4: Advanced Features (2-3 weeks)
1. **Key Rotation**:
   - Implement `kid` (Key ID) support
   - JWKS with multiple keys
   - Automated key rotation schedule

2. **Token Revocation**:
   - Admin API for token revocation
   - Cleanup expired revoked tokens
   - Real-time revocation checks

## Testing Strategy

### Unit Tests Required
1. **Algorithm Migration Tests**:
   ```python
   async def test_rs256_token_creation():
       """Test RS256 token creation with enhanced claims."""

   async def test_dual_algorithm_verification():
       """Test both HS256 and RS256 token verification during transition."""
   ```

2. **Security Claims Tests**:
   ```python
   async def test_audience_validation():
       """Test audience claim validation prevents cross-service token use."""

   async def test_token_revocation():
       """Test revoked tokens are rejected."""
   ```

3. **JWKS Tests**:
   ```python
   async def test_jwks_endpoint():
       """Test JWKS endpoint returns valid key set."""
   ```

### Integration Tests
1. **Full Authentication Flow**: User login → Token creation → API access
2. **Service Token Flow**: Token generation → Deployment initiation
3. **WebSocket Authentication**: Token validation in real-time connections

### Security Tests
1. **Token Forgery Prevention**: Verify old symmetric key cannot create valid asymmetric tokens
2. **Cross-Service Token Abuse**: Verify audience validation prevents token misuse
3. **Revocation Effectiveness**: Verify revoked tokens are immediately rejected

## Deployment Considerations

### Infrastructure Requirements
1. **Key Management**:
   - Secure storage for RSA private keys (consider HSM for production)
   - Key backup and recovery procedures
   - Automated key rotation infrastructure

2. **Configuration Updates**:
   ```bash
   # New environment variables
   PRIVATE_KEY_PATH=/etc/fastdeploy/keys/private.pem
   PUBLIC_KEY_PATH=/etc/fastdeploy/keys/public.pem
   KEY_PASSPHRASE=<secure-passphrase>
   ```

3. **Monitoring & Alerting**:
   - Monitor JWKS endpoint availability
   - Alert on key loading failures
   - Track token revocation rates

### Rollback Plan
1. **Emergency Rollback**: Keep HS256 verification active during transition
2. **Configuration Rollback**: Ability to switch back to `HS256` via environment variable
3. **Database Rollback**: Revocation table can be ignored safely

## Recommendation

**IMPLEMENT IMMEDIATELY** - This is a critical security vulnerability that should be addressed as high priority:

### Immediate Actions (Week 1)
1. ✅ **Audit Current Token Usage**: Document all token creation/verification points
2. ✅ **Generate RSA Key Pair**: Create production-ready asymmetric keys
3. ✅ **Plan Migration Timeline**: 4-6 week gradual migration to minimize disruption

### Short Term (Weeks 2-4)
4. ✅ **Implement Dual Algorithm Support**: Allow both HS256 and RS256 during transition
5. ✅ **Add Enhanced Security Claims**: Implement `aud`, `nbf`, `jti` validation
6. ✅ **Deploy JWKS Endpoint**: Enable token verification without shared secrets

### Medium Term (Weeks 5-8)
7. ✅ **Implement Token Revocation**: Database-backed individual token invalidation
8. ✅ **Phase Out HS256**: Complete migration to asymmetric signing only
9. ✅ **Add Key Rotation**: Automated key management with `kid` support

### Success Metrics
- ✅ Zero shared secrets for token verification
- ✅ Individual token revocation capability
- ✅ Audience-based token scope limitation
- ✅ Complete audit trail of token lifecycle

This migration addresses the core security concern while maintaining system availability and providing a clear path to enhanced JWT security practices.
