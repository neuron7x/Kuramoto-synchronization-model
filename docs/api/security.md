# TradePulse API Security Guide

Comprehensive security documentation for the TradePulse API.

## Table of Contents

1. [Authentication](#authentication)
2. [Authorization](#authorization)
3. [Transport Security](#transport-security)
4. [Admin Endpoints Security](#admin-endpoints-security)
5. [API Keys & Token Management](#api-keys--token-management)
6. [Rate Limiting & Abuse Prevention](#rate-limiting--abuse-prevention)
7. [Request Validation](#request-validation)
8. [Security Headers](#security-headers)
9. [Audit Logging](#audit-logging)
10. [Best Practices](#best-practices)

## Authentication

### OAuth 2.0 Bearer Tokens

The TradePulse API uses OAuth 2.0 for authentication. All requests must include a valid Bearer token in the `Authorization` header.

#### Token Requirements

- **Issuer**: Must match configured OAuth2 provider
- **Audience**: `tradepulse-api`
- **Algorithm**: RS256 (RSA Signature with SHA-256)
- **Required Scopes**:
  - `api:read` - Read access to endpoints
  - `api:write` - Write access to endpoints
  - `admin:execute` - Admin endpoint access (admin only)

#### Example Token Claims

```json
{
  "iss": "https://auth.tradepulse.example.com",
  "sub": "user-12345",
  "aud": "tradepulse-api",
  "exp": 1704067200,
  "iat": 1704063600,
  "scope": "api:read api:write",
  "email": "trader@example.com",
  "email_verified": true
}
```

#### Usage

```http
GET /api/v1/features HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Token Validation

The API validates tokens by:

1. **Signature Verification**: Using JWKS from OAuth2 provider
2. **Expiration Check**: Tokens must not be expired
3. **Audience Validation**: Must match `tradepulse-api`
4. **Issuer Validation**: Must match configured issuer
5. **Scope Verification**: Must have required scopes

#### Error Responses

**401 Unauthorized - Missing Token**
```json
{
  "detail": {
    "code": "UNAUTHORIZED",
    "message": "Bearer token required for this endpoint."
  }
}
```

**401 Unauthorized - Invalid Token**
```json
{
  "detail": {
    "code": "INVALID_TOKEN",
    "message": "Token signature verification failed."
  }
}
```

**403 Forbidden - Insufficient Scope**
```json
{
  "detail": {
    "code": "INSUFFICIENT_SCOPE",
    "message": "Token does not have required scope: api:write"
  }
}
```

## Authorization

### Role-Based Access Control (RBAC)

The API implements fine-grained RBAC using permissions.

#### Permission Model

Permissions follow the format: `resource.action`

Examples:
- `api.read` - Read public API endpoints
- `api.write` - Write to public API endpoints
- `risk.kill_switch.read` - View kill-switch status
- `risk.kill_switch.execute` - Engage/reset kill-switch

#### Permission Checks

```python
# Example: Check if user can execute kill-switch
from application.api.authorization import require_permission

@app.post("/admin/kill-switch")
async def engage_kill_switch(
    identity: AdminIdentity = Depends(two_factor_auth),
    _permission: None = Depends(
        require_permission("risk.kill_switch", "execute")
    )
):
    # User has required permission
    pass
```

#### Attribute-Based Access Control (ABAC)

Additional context attributes:
- `environment` - Deployment environment (production/staging)
- `ip_address` - Client IP address
- `time_of_day` - Request timestamp
- `resource_tags` - Resource-specific tags

### Access Control Lists (ACLs)

Configure access policies in your OAuth2 provider or access control system:

```yaml
# Example policy configuration
policies:
  - name: trading_team
    subjects:
      - user:trader@example.com
      - group:trading-team
    permissions:
      - api.read
      - api.write
    conditions:
      environment: production
      
  - name: risk_managers
    subjects:
      - group:risk-management
    permissions:
      - risk.kill_switch.read
      - risk.kill_switch.execute
    conditions:
      requires_2fa: true
```

## Transport Security

### TLS Configuration

All API communication must use TLS 1.3 (minimum TLS 1.2).

**Cipher Suites (Preferred Order):**
1. `TLS_AES_256_GCM_SHA384`
2. `TLS_CHACHA20_POLY1305_SHA256`
3. `TLS_AES_128_GCM_SHA256`

**Certificate Requirements:**
- Valid certificate chain
- Certificate Authority (CA) trusted by major browsers
- Subject Alternative Name (SAN) matching API domain
- Key size: RSA 2048-bit minimum or ECDSA P-256+
- Certificate transparency (CT) logging

### Certificate Pinning

For enhanced security, implement certificate pinning:

```python
import ssl
import certifi

def create_pinned_context():
    context = ssl.create_default_context(cafile=certifi.where())
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context

# Usage
import requests
session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(
    max_retries=3,
    pool_connections=10,
    pool_maxsize=10,
))
response = session.get(
    'https://api.tradepulse.example.com/health',
    verify=True  # Always verify certificates
)
```

### HSTS (HTTP Strict Transport Security)

The API sets HSTS headers:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

## Admin Endpoints Security

Admin endpoints require enhanced security measures.

### Three-Factor Authentication

1. **OAuth 2.0 Token** - Bearer token with admin scope
2. **Mutual TLS (mTLS)** - Client certificate verification
3. **Time-Based One-Time Password (TOTP)** - 2FA code

#### mTLS Configuration

**Client Certificate Requirements:**
- Issued by TradePulse platform CA
- Valid certificate chain
- Not expired or revoked
- Subject DN matches authorized list

**Example Request:**
```bash
curl --cert client.pem --key client-key.pem \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "X-TradePulse-2FA: 123456" \
  https://api.tradepulse.example.com/admin/kill-switch
```

#### TOTP (Two-Factor Authentication)

**Configuration:**
- Algorithm: SHA-1 (standard TOTP)
- Digits: 6
- Period: 30 seconds
- Allowed drift: ±1 window (±30 seconds)

**Setup Process:**

1. Generate TOTP secret (base32 encoded)
2. Share via secure channel
3. Store in authenticator app (Google Authenticator, Authy, etc.)
4. Include code in `X-TradePulse-2FA` header

**Example Code Generation:**

```python
import pyotp

# Administrator receives secret securely
secret = "BASE32ENCODEDSECRET"
totp = pyotp.TOTP(secret)

# Generate current code
current_code = totp.now()  # e.g., "123456"

# Verify code (server-side)
is_valid = totp.verify(current_code, valid_window=1)
```

#### Admin Rate Limits

Stricter limits for admin endpoints:
- **30 requests per minute** per admin identity
- **Exponential backoff required** on rate limit

### Kill-Switch Permissions

```python
# Example permission check
@app.post("/admin/kill-switch")
async def engage_kill_switch(
    request: Request,
    identity: AdminIdentity = Depends(require_bearer_with_mtls),
    _two_factor: None = Depends(require_two_factor),
    _permission: None = Depends(
        require_permission("risk.kill_switch", "execute",
                          attributes_provider=lambda r, i: {
                              "environment": "production",
                              "ip_address": r.client.host
                          })
    )
):
    # All checks passed
    pass
```

## API Keys & Token Management

### Token Lifecycle

1. **Generation**: Obtain from OAuth2 provider
2. **Storage**: Store securely (never in code)
3. **Usage**: Include in Authorization header
4. **Rotation**: Rotate regularly (recommended: 90 days)
5. **Revocation**: Revoke immediately if compromised

### Secure Storage

**❌ Don't Do This:**
```python
# NEVER hardcode tokens
API_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**✅ Do This:**
```python
# Use environment variables
import os
API_TOKEN = os.environ['TRADEPULSE_API_TOKEN']

# Or use secret management
from application.secrets import get_secret
API_TOKEN = get_secret('tradepulse/api/token')
```

### Token Rotation

```python
class TokenManager:
    def __init__(self, oauth_client):
        self.oauth_client = oauth_client
        self.current_token = None
        self.token_expires_at = None
    
    def get_token(self):
        """Get valid token, refreshing if needed."""
        if self._is_expired():
            self._refresh_token()
        return self.current_token
    
    def _is_expired(self):
        if not self.token_expires_at:
            return True
        # Refresh 5 minutes before expiry
        return time.time() > (self.token_expires_at - 300)
    
    def _refresh_token(self):
        response = self.oauth_client.get_token()
        self.current_token = response['access_token']
        self.token_expires_at = time.time() + response['expires_in']
```

### Secret Management

Use dedicated secret management systems:

#### HashiCorp Vault

```python
import hvac

client = hvac.Client(url='https://vault.example.com')
client.token = os.environ['VAULT_TOKEN']

# Read secret
secret = client.secrets.kv.v2.read_secret_version(
    path='tradepulse/api/token'
)
api_token = secret['data']['data']['token']
```

#### AWS Secrets Manager

```python
import boto3

client = boto3.client('secretsmanager')
response = client.get_secret_value(SecretId='tradepulse/api/token')
api_token = json.loads(response['SecretString'])['token']
```

#### Azure Key Vault

```python
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url="https://tradepulse.vault.azure.net",
    credential=credential
)
api_token = client.get_secret("tradepulse-api-token").value
```

## Rate Limiting & Abuse Prevention

### Rate Limit Tiers

| Tier | Requests/Minute | Notes |
|------|----------------|-------|
| Public | 100 | Standard endpoints |
| Admin | 30 | Administrative endpoints |
| Burst | +20% | Temporary burst allowance |

### Algorithm

Sliding window rate limiting with per-user and per-IP tracking.

### Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067200
Retry-After: 60
```

### Client Implementation

```python
import time

class RateLimitedClient:
    def __init__(self, base_client):
        self.client = base_client
        self.request_count = 0
        self.window_start = time.time()
        self.max_requests = 100
        self.window_seconds = 60
    
    def _wait_if_needed(self):
        elapsed = time.time() - self.window_start
        
        if elapsed >= self.window_seconds:
            # Reset window
            self.request_count = 0
            self.window_start = time.time()
        elif self.request_count >= self.max_requests:
            # Wait for window to reset
            sleep_time = self.window_seconds - elapsed
            time.sleep(sleep_time)
            self.request_count = 0
            self.window_start = time.time()
    
    def request(self, *args, **kwargs):
        self._wait_if_needed()
        self.request_count += 1
        return self.client.request(*args, **kwargs)
```

### Abuse Prevention

Additional protections:

1. **IP Blocking**: Automatic blocking of abusive IPs
2. **Anomaly Detection**: ML-based detection of unusual patterns
3. **Captcha**: Required after repeated 429 responses
4. **Account Lockout**: Temporary suspension after abuse

## Request Validation

### Input Sanitization

All inputs are validated:

1. **Schema Validation**: Pydantic models
2. **Type Checking**: Strict type enforcement
3. **Range Validation**: Min/max constraints
4. **Pattern Matching**: Regex validation
5. **Sanitization**: Remove dangerous characters

### Example

```python
from pydantic import BaseModel, Field, validator

class FeatureRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20, pattern=r'^[A-Z0-9-/]+$')
    bars: list[MarketBar] = Field(..., min_length=1, max_length=1000)
    
    @validator('symbol')
    def sanitize_symbol(cls, v):
        # Remove potentially dangerous characters
        return v.upper().strip()
```

### Payload Size Limits

```python
# Maximum request sizes
MAX_REQUEST_BODY_BYTES = 1_048_576  # 1 MB
MAX_BARS_PER_REQUEST = 1000
MAX_FEATURE_KEYS = 100
```

### Suspicious Payload Detection

The API rejects requests containing:

- SQL injection patterns
- Script tags (`<script>`)
- Command injection attempts
- Path traversal sequences (`../`)
- Null bytes
- Control characters

## Security Headers

### Response Headers

Every response includes security headers:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### CORS Configuration

```http
Access-Control-Allow-Origin: https://app.tradepulse.example.com
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-ID
Access-Control-Max-Age: 86400
Access-Control-Allow-Credentials: false
```

### Cache Control

```http
# Public endpoints
Cache-Control: private, max-age=30

# Admin endpoints
Cache-Control: no-store
Pragma: no-cache
```

## Audit Logging

### Logged Events

All security-relevant events are logged:

1. **Authentication**
   - Successful logins
   - Failed login attempts
   - Token validation failures
   - Token expiration

2. **Authorization**
   - Permission checks
   - Access denials
   - Role changes

3. **Admin Actions**
   - Kill-switch engagement
   - Kill-switch reset
   - Configuration changes

4. **Security Events**
   - Rate limit violations
   - Suspicious requests
   - Error patterns

### Audit Log Format

```json
{
  "timestamp": "2025-01-01T00:00:00Z",
  "event_type": "authentication.success",
  "actor": {
    "id": "user-12345",
    "email": "trader@example.com",
    "ip_address": "192.0.2.1"
  },
  "resource": {
    "type": "api_endpoint",
    "path": "/api/v1/predictions"
  },
  "action": "POST",
  "result": "success",
  "metadata": {
    "user_agent": "TradePulse-Client/1.0",
    "request_id": "req-abc123",
    "duration_ms": 145
  }
}
```

### Audit Trail Access

Audit logs are:
- **Tamper-proof**: Append-only with integrity verification
- **Encrypted**: At rest and in transit
- **Retained**: 400 days minimum
- **Searchable**: Via SIEM integration
- **Compliant**: GDPR, CCPA, SOC 2

### Query Audit Logs

```python
from observability.audit.trail import get_access_audit_trail

audit_trail = get_access_audit_trail()

# Query specific user
events = audit_trail.query(
    actor_id="user-12345",
    start_time="2025-01-01T00:00:00Z",
    end_time="2025-01-02T00:00:00Z"
)

# Query by event type
admin_actions = audit_trail.query(
    event_type="admin.*",
    limit=100
)
```

## Best Practices

### 1. Token Security

- ✅ **DO**: Store tokens in secure storage (vault, environment variables)
- ✅ **DO**: Use short-lived tokens with refresh mechanism
- ✅ **DO**: Implement token rotation
- ❌ **DON'T**: Hardcode tokens in source code
- ❌ **DON'T**: Log tokens
- ❌ **DON'T**: Include tokens in URLs

### 2. Transport Security

- ✅ **DO**: Always use HTTPS
- ✅ **DO**: Verify TLS certificates
- ✅ **DO**: Pin certificates for critical applications
- ❌ **DON'T**: Disable certificate validation
- ❌ **DON'T**: Use self-signed certificates in production
- ❌ **DON'T**: Allow fallback to HTTP

### 3. Error Handling

- ✅ **DO**: Handle errors gracefully
- ✅ **DO**: Log errors with context
- ✅ **DO**: Provide generic error messages to clients
- ❌ **DON'T**: Expose internal details in errors
- ❌ **DON'T**: Log sensitive data
- ❌ **DON'T**: Ignore security errors

### 4. Rate Limiting

- ✅ **DO**: Implement client-side rate limiting
- ✅ **DO**: Respect Retry-After headers
- ✅ **DO**: Use exponential backoff
- ❌ **DON'T**: Spam the API
- ❌ **DON'T**: Ignore 429 responses
- ❌ **DON'T**: Use multiple tokens to bypass limits

### 5. Monitoring

- ✅ **DO**: Monitor authentication failures
- ✅ **DO**: Alert on unusual patterns
- ✅ **DO**: Track permission denials
- ✅ **DO**: Review audit logs regularly
- ❌ **DON'T**: Ignore security alerts
- ❌ **DON'T**: Disable logging

### 6. Incident Response

- ✅ **DO**: Have an incident response plan
- ✅ **DO**: Revoke compromised tokens immediately
- ✅ **DO**: Document security incidents
- ✅ **DO**: Conduct post-mortems
- ❌ **DON'T**: Delay incident response
- ❌ **DON'T**: Hide security issues

## Security Contacts

### Report Security Issues

**Email**: security@tradepulse.example  
**PGP Key**: [security-pgp.asc](../../SECURITY.md)

### Response Times

- **Critical**: 4 hours
- **High**: 24 hours
- **Medium**: 7 days
- **Low**: 30 days

### Disclosure Policy

We follow responsible disclosure:

1. Report received and acknowledged
2. Issue verified and assessed
3. Fix developed and tested
4. Security advisory published (after fix deployed)
5. Credit given to reporter (if desired)

## Compliance

The TradePulse API security framework complies with:

- ✅ **GDPR** - General Data Protection Regulation
- ✅ **CCPA** - California Consumer Privacy Act
- ✅ **SOC 2 Type II** - Service Organization Control
- ✅ **ISO 27001** - Information Security Management
- ✅ **NIST SP 800-53** - Security and Privacy Controls
- ✅ **PCI DSS** - Payment Card Industry Data Security Standard (if applicable)
- ✅ **MiFID II** - Markets in Financial Instruments Directive
- ✅ **SEC** - Securities and Exchange Commission regulations
- ✅ **FINRA** - Financial Industry Regulatory Authority requirements

## Security Checklist

Use this checklist when integrating with the API:

- [ ] Tokens stored securely (not in code)
- [ ] HTTPS enforced (never HTTP)
- [ ] Certificate validation enabled
- [ ] Rate limiting implemented
- [ ] Error handling configured
- [ ] Audit logging enabled
- [ ] Monitoring alerts configured
- [ ] Incident response plan documented
- [ ] Token rotation schedule defined
- [ ] Security contacts identified
- [ ] Compliance requirements verified
- [ ] Security review completed

---

**Last Updated**: 2025-01-10  
**Security Contact**: security@tradepulse.example  
**Bug Bounty**: [hackerone.com/tradepulse](https://hackerone.com/tradepulse)
