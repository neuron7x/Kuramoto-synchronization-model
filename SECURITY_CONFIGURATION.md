# Security Configuration Guide

This document provides guidance on configuring TradePulse securely for production deployment.

## Table of Contents

- [Admin API Security](#admin-api-security)
- [Environment Variables](#environment-variables)
- [Network Security](#network-security)
- [Authentication & Authorization](#authentication--authorization)
- [Rate Limiting](#rate-limiting)
- [Logging & Monitoring](#logging--monitoring)
- [File Security](#file-security)
- [Best Practices](#best-practices)

## Admin API Security

The Admin API provides critical risk control endpoints (kill switch, risk state). It **must** be properly secured in production.

### Default Security Posture

By default, the Admin API:
- Binds to `127.0.0.1` (localhost only)
- Requires bearer token authentication
- Enforces rate limiting (10 requests/minute per IP)
- Adds comprehensive security headers
- Logs all authentication attempts and actions

### Required Configuration

**CRITICAL**: Before deploying to production, you **must** set:

```bash
# Generate a secure random token (at least 32 characters)
export ADMIN_API_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

**Never** use default or weak tokens in production!

### Network Binding

**Localhost Only (Recommended)**:
```bash
export ADMIN_API_HOST=127.0.0.1
export ADMIN_API_PORT=8000
```

This is the secure default. Access the API through:
- SSH tunnel: `ssh -L 8000:localhost:8000 user@server`
- VPN with local access
- Reverse proxy (nginx, Caddy) with its own authentication

**WARNING**: Only bind to `0.0.0.0` if you have:
1. Proper firewall rules restricting access
2. Additional authentication layer (OAuth, mTLS)
3. WAF (Web Application Firewall) in front
4. VPN or private network isolation

### Security Headers

The Admin API automatically adds:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Environment Variables

### Required for Production

```bash
# Admin API Authentication
ADMIN_API_TOKEN=<generate-strong-random-token>

# Database Credentials
POSTGRES_PASSWORD=<strong-password>
DATABASE_URL=postgresql://user:password@localhost:5432/tradepulse

# Application Secrets
SECRET_KEY=<generate-strong-random-key>
JWT_SECRET=<generate-strong-random-key>
TRADEPULSE_AUDIT_SECRET=<generate-strong-random-key>
TRADEPULSE_RBAC_AUDIT_SECRET=<generate-strong-random-key>

# Exchange API Keys (use read-only or restricted keys when possible)
BINANCE_API_KEY=<your-api-key>
BINANCE_API_SECRET=<your-api-secret>
```

### Optional Security Settings

```bash
# Admin API Network
ADMIN_API_HOST=127.0.0.1  # localhost only (default)
ADMIN_API_PORT=8000

# Rate Limiting
ADMIN_API_RATE_LIMIT_MAX=10  # requests per window
ADMIN_API_RATE_LIMIT_WINDOW=60  # seconds

# CORS (restrict to your domains)
ADMIN_API_CORS_ORIGINS=https://your-dashboard.com,https://your-app.com

# General Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_CALLS=100
RATE_LIMIT_PERIOD=60
```

## Network Security

### Firewall Configuration

If you must bind to `0.0.0.0`, configure firewall rules:

**Linux (iptables)**:
```bash
# Allow only from specific IPs
iptables -A INPUT -p tcp --dport 8000 -s 10.0.1.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -j DROP
```

**Linux (ufw)**:
```bash
# Allow only from specific IPs
ufw allow from 10.0.1.0/24 to any port 8000
ufw deny 8000
```

### Reverse Proxy (Recommended)

Use nginx or Caddy as a reverse proxy with additional security:

**nginx example**:
```nginx
server {
    listen 443 ssl http2;
    server_name admin.tradepulse.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # Additional authentication
    auth_basic "Admin Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    # IP whitelist
    allow 10.0.1.0/24;
    deny all;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Authentication & Authorization

### Token Management

**Generation**:
```python
import secrets
token = secrets.token_urlsafe(32)  # At least 32 characters
```

**Storage**:
- Use environment variables (not in code)
- Use secrets management (HashiCorp Vault, AWS Secrets Manager)
- Rotate tokens regularly (every 90 days minimum)
- Use different tokens for dev/staging/prod

**Usage**:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/admin/risk/state
```

### Role-Based Access Control

The Admin API endpoints are high-privilege operations. Consider:
1. Separate tokens for different admin roles
2. Audit logging of all token usage
3. Token expiration and rotation policies
4. Multi-factor authentication for token issuance

## Rate Limiting

### Configuration

Default: 10 requests per minute per IP

```bash
# Adjust based on your needs
export ADMIN_API_RATE_LIMIT_MAX=10
export ADMIN_API_RATE_LIMIT_WINDOW=60
```

### Production Considerations

For production, consider:
- Using Redis for distributed rate limiting
- Different limits per endpoint
- Exponential backoff for repeated violations
- IP blacklisting after threshold violations

## Logging & Monitoring

### Audit Logging

All Admin API activity is logged:
- Authentication attempts (success/failure)
- Kill switch toggles
- Risk state queries
- Rate limit violations

**Log locations**:
- Application logs: As configured in `LOG_FILE`
- Security events: Separate audit log recommended

### Monitoring

Set up alerts for:
- Failed authentication attempts
- Kill switch activations
- Rate limit violations
- Unusual access patterns
- Error rate spikes

## File Security

### YAML Configuration Files

Configuration files are validated for:
- File existence and readability
- File size limits (10 MB max)
- Valid YAML syntax
- Required structure

**Best practices**:
```bash
# Set appropriate permissions
chmod 600 config/nak.yaml
chown tradepulse:tradepulse config/nak.yaml

# Validate before deployment
python -c "import yaml; yaml.safe_load(open('config/nak.yaml'))"
```

### Secrets in Files

**NEVER** store secrets in:
- Configuration files in git
- Example files
- Documentation
- Log files

**DO** use:
- Environment variables
- Secrets management systems
- Encrypted configuration (with external key)

## Best Practices

### Production Checklist

- [ ] Generate strong random tokens (32+ characters)
- [ ] Set `ADMIN_API_HOST=127.0.0.1` (or use VPN/firewall)
- [ ] Configure rate limiting appropriately
- [ ] Set up audit logging
- [ ] Enable monitoring and alerts
- [ ] Use HTTPS/TLS (via reverse proxy)
- [ ] Implement token rotation policy
- [ ] Restrict CORS origins
- [ ] Review and minimize exposed endpoints
- [ ] Set up WAF if exposing to internet
- [ ] Enable IP whitelisting
- [ ] Use separate credentials per environment
- [ ] Document security procedures
- [ ] Plan incident response procedures
- [ ] Regular security audits

### Security Updates

Stay informed about security updates:
1. Subscribe to TradePulse security advisories
2. Monitor dependency vulnerabilities
3. Keep dependencies up to date
4. Review security logs regularly
5. Conduct periodic security assessments

### Incident Response

If you suspect a security breach:
1. Immediately rotate all tokens and secrets
2. Check audit logs for unauthorized access
3. Review recent configuration changes
4. Enable kill switch if trading is affected
5. Contact security team
6. Document the incident
7. Conduct post-mortem analysis

## Additional Resources

- [SECURITY.md](SECURITY.md) - Vulnerability reporting
- [SECURITY_FRAMEWORK_SUMMARY.md](SECURITY_FRAMEWORK_SUMMARY.md) - Security framework
- [.env.example](.env.example) - Environment variable examples
- [SECURITY_OPERATIONS_GUIDE.md](docs/security/SECURITY_OPERATIONS_GUIDE.md) - Detailed operations guide

## Questions?

For security concerns or questions:
- Review existing documentation
- Check GitHub issues
- Contact the security team (see SECURITY.md)

**Remember**: Security is a shared responsibility. Always follow the principle of least privilege and defense in depth.
