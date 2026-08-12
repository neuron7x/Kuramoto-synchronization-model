# Administrative Kill-Switch Remote Control

This guide explains how to enable and operate the secure administrative kill-switch endpoint shipped with GeoSync.

## Overview

GeoSync exposes a protected FastAPI surface at `/admin/kill-switch` that lets on-call operators inspect, engage, and reset the global `RiskManager` kill-switch. When the switch is engaged, all new orders are rejected to prevent further trading activity while the incident is being investigated.

Key properties:

- **OAuth2 + mTLS protected** – OAuth2 bearer tokens are validated against the configured issuer and JWKS, and mutual TLS client certificates are required for state-changing operations.
- **Audited** – every action is recorded through the structured audit logger with a tamper-evident HMAC signature.
- **Idempotent** – repeated requests while the switch is active are acknowledged and logged as reaffirmations, and resets that find the switch already clear are logged as no-ops.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/admin/kill-switch` | Return the current kill-switch status without mutating it. |
| `POST` | `/admin/kill-switch` | Engage (or reaffirm) the kill-switch with an operator-provided reason. |
| `DELETE` | `/admin/kill-switch` | Reset the kill-switch; repeated invocations remain idempotent. |

The canonical OpenAPI schema for these operations lives at [`docs/api/admin_remote_control_openapi.yaml`](api/admin_remote_control_openapi.yaml).

## Configuration

Set the following environment variables before starting the FastAPI application:

| Variable | Description |
| --- | --- |
| `GEOSYNC_AUDIT_SECRET` | Secret used to sign audit records for integrity verification. |
| `GEOSYNC_AUDIT_SECRET_PATH` | Optional file path populated by your secret manager. When provided the service refreshes the signing key without restarts. |
| `GEOSYNC_SECRET_REFRESH_INTERVAL_SECONDS` | Interval in seconds between secret refresh attempts (default `300`). |
| `GEOSYNC_OAUTH2_ISSUER` | OAuth2/OpenID Connect issuer expected in bearer token `iss` claims. |
| `GEOSYNC_OAUTH2_AUDIENCE` | Audience that must be present in validated JWT access tokens. |
| `GEOSYNC_OAUTH2_JWKS_URI` | HTTPS JWKS endpoint used to resolve signing keys. |
| `GEOSYNC_ADMIN_SUBJECT` | Default subject recorded for audit events when the identity provider omits the `sub` claim. |
| `GEOSYNC_ADMIN_RATE_LIMIT_MAX_ATTEMPTS` | Maximum administrative attempts allowed within the rate-limit window (default `5`). |
| `GEOSYNC_ADMIN_RATE_LIMIT_INTERVAL_SECONDS` | Rolling window in seconds for the administrative rate limiter (default `60`). |
| `GEOSYNC_AUDIT_WEBHOOK_URL` | Optional HTTPS endpoint that receives a JSON copy of every administrative audit event. |
| `GEOSYNC_SIEM_CLIENT_SECRET_PATH` | Optional file path containing the SIEM API client secret. Can be used instead of `GEOSYNC_SIEM_CLIENT_SECRET`. |
| `GEOSYNC_MTLS_TRUSTED_CA_PATH` | Filesystem path to the trusted client CA bundle used for mutual TLS handshakes. |
| `GEOSYNC_MTLS_REVOCATION_LIST_PATH` | Optional path to a PEM encoded certificate revocation list enforced during mTLS validation. |

> **Important:** Development defaults are provided for the audit logger to simplify local testing. Always supply production OAuth2 credentials and TLS assets before deploying.

> **Note:** `GEOSYNC_AUDIT_SECRET` must contain at least 16 characters. When mounting file-based secrets ensure your secret manager renews them before expiry so the runtime refresh (controlled by `GEOSYNC_SECRET_REFRESH_INTERVAL_SECONDS`) picks up the rotation.

### TLS and client certificates

- Terminate TLS with a certificate issued by an internal or commercial CA.
- Configure the ingress or ASGI server with the trusted client CA bundle referenced by `GEOSYNC_MTLS_TRUSTED_CA_PATH` and optional CRL at `GEOSYNC_MTLS_REVOCATION_LIST_PATH`.
- Ensure the server forwards validated client certificate details (for example, by populating the `X-Client-Cert` header or the ASGI `client_cert` scope entry).

## Request Flow

1. **Inspect state:**
   ```bash
   curl -H "Authorization: Bearer $OAUTH_ACCESS_TOKEN" \
        --cert client.pem --key client.key \
        https://risk.geosync.example.com/admin/kill-switch
   ```
2. **Engage / reaffirm:**
   ```bash
   curl -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $OAUTH_ACCESS_TOKEN" \
        --cert client.pem --key client.key \
        -d '{"reason": "manual intervention after monitoring alert"}' \
        https://risk.geosync.example.com/admin/kill-switch
   ```
3. **Reset:**
   ```bash
   curl -X DELETE \
        -H "Authorization: Bearer $OAUTH_ACCESS_TOKEN" \
        --cert client.pem --key client.key \
        https://risk.geosync.example.com/admin/kill-switch
   ```

## Responses

A successful engagement returns:

```json
{
  "status": "engaged",
  "kill_switch_engaged": true,
  "reason": "manual intervention after monitoring alert",
  "already_engaged": false
}
```

If the switch was previously active, `status` becomes `"already-engaged"` and `already_engaged` is `true`.

A reset that clears an active switch returns:

```json
{
  "status": "reset",
  "kill_switch_engaged": false,
  "reason": "manual intervention after monitoring alert",
  "already_engaged": true
}
```

If the switch is already clear the API responds with `status` `"already-clear"` while keeping `already_engaged` `false` to signal that no change was required. Reads return `"engaged"` or `"disengaged"` depending on the current state.

## Audit Logging

Audit events include the following fields:

- `event_type`: `kill_switch_state_viewed`, `kill_switch_engaged`, `kill_switch_reaffirmed`, `kill_switch_reset`, or `kill_switch_reset_noop`
- `actor`: Administrator subject (from `X-Admin-Subject` or default)
- `ip_address`: Remote IP extracted from the request
- `details`: Structured metadata containing the provided reason and whether the switch was already active
- `signature`: HMAC-SHA256 signature computed with `GEOSYNC_AUDIT_SECRET`

Signed entries are written through to an append-only audit ledger before they are mirrored to external sinks. The default
implementation persists JSON Lines entries (one record per line) and performs an `fsync` after every write to guarantee
durability. Downstream forwarding to the security information and event management (SIEM) endpoint uses a durable spool
directory with exponential backoff; failed deliveries are retried automatically and exhausted attempts land in a
dead-letter queue for manual intervention.

Use `AuditLogger.verify(record)` to validate stored entries if tampering is suspected. The verification flow should be
scheduled as part of your compliance checks:

1. Export the append-only ledger and reconstitute each JSON object.
2. Instantiate `AuditLogger` with the signing secret (for example via `GEOSYNC_AUDIT_SECRET`).
3. Call `verify` on every record and alert if any signature fails.

### Retention and SIEM Configuration

- **Retention** – Store the append-only files (or database table) on immutable storage with your standard retention
  policy. Replicate or snapshot the ledger at least daily to cold storage. Keep the SIEM dead-letter directory under the
  same retention window so failures remain auditable.
- **SIEM forwarding** – Configure the endpoint and credentials through the following settings:
  - `GEOSYNC_SIEM_ENDPOINT`
  - `GEOSYNC_SIEM_CLIENT_ID`
  - `GEOSYNC_SIEM_CLIENT_SECRET` (inject via `/run/secrets` or your secret manager)
  - `GEOSYNC_SIEM_SCOPE` (optional)
- **Verification drills** – Review the dead-letter queue during weekly operations reviews and requeue items after the
  upstream outage is resolved.

## Testing

Run the dedicated unit tests with:

```bash
pytest tests/admin/test_remote_control.py
```

The suite validates authentication, kill-switch semantics, and audit logging integrity.

## Production Recommendations

- Integrate with your organisation's OAuth2/OpenID Connect provider and rotate credentials regularly. Access tokens should be short-lived with refresh performed by trusted automation.
- Persist audit records to an append-only datastore (JSON Lines ledger, immutable object store, or database table with
  `INSERT`-only trigger protections).
- Monitor the SIEM spool and dead-letter directories; alerts should fire if the queue size grows unexpectedly or records
  remain in dead-letter beyond your defined service-level objective.
- Configure alerts on the `kill_switch_reaffirmed` and `kill_switch_reset_noop` events to avoid unnoticed overrides or repeated ineffective resets.
- Integrate the kill-switch status into your incident response runbooks so that restarts include a reset step if appropriate, using the `DELETE /admin/kill-switch` endpoint for consistency with audit trails.
