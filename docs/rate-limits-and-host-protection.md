# Rate limiting and host protection

GeoSync now exposes configurable knobs for the operations team to tune per-client
quotas and ingress filtering. This document summarises the key environment variables
and the recommended workflow when rolling out changes.

## Per-client rate policies

Rate limits are managed by `ApiRateLimitSettings` which reads configuration from the
`GEOSYNC_RATE_*` environment variables.

| Setting | Environment variable | Description |
| --- | --- | --- |
| `default_policy` | `GEOSYNC_RATE_DEFAULT_POLICY` | JSON object defining `max_requests` and `window_seconds` for authenticated subjects without a dedicated override. |
| `unauthenticated_policy` | `GEOSYNC_RATE_UNAUTHENTICATED_POLICY` | Optional JSON object that constrains unauthenticated/IP keyed requests. When omitted the default policy applies. |
| `client_policies` | `GEOSYNC_RATE_CLIENT_POLICIES` | JSON object mapping authenticated subjects (API keys or mTLS subjects) to individual policies. |
| `redis_url` | `GEOSYNC_RATE_REDIS_URL` | Redis URI used to coordinate limits across multiple application instances. |
| `redis_key_prefix` | `GEOSYNC_RATE_REDIS_KEY_PREFIX` | Prefix applied to Redis keys when coordinating quotas. |

### Example: dedicate a burstier policy to a specific subject

```bash
export GEOSYNC_RATE_DEFAULT_POLICY='{"max_requests": 120, "window_seconds": 60}'
export GEOSYNC_RATE_CLIENT_POLICIES='{"vip-client": {"max_requests": 240, "window_seconds": 60}}'
export GEOSYNC_RATE_REDIS_URL='redis://cache.internal:6379/0'
```

After updating the environment, redeploy the service. The FastAPI application will
initialise a Redis-backed sliding-window limiter automatically when `redis_url` is
provided.

### Operational checklist

1. Update the appropriate `GEOSYNC_RATE_*` variables for your environment.
2. Ensure Redis connectivity (TLS, authentication) is configured before rolling
   out a clustered deployment.
3. Restart the application pods and monitor the `429` metrics for unexpected spikes.
4. Document subject-specific overrides in your runbooks to help support teams.

## Host allow-list and payload inspection

`ApiSecuritySettings` now includes defensive defaults that can be overridden via
environment variables with the `GEOSYNC_` prefix.

| Setting | Environment variable | Description |
| --- | --- | --- |
| `trusted_hosts` | `GEOSYNC_TRUSTED_HOSTS` | Comma-separated list or JSON array of host headers accepted by the API gateway. |
| `max_request_bytes` | `GEOSYNC_MAX_REQUEST_BYTES` | Maximum payload size (in bytes) accepted before rejecting with HTTP 413. |
| `suspicious_json_keys` | `GEOSYNC_SUSPICIOUS_JSON_KEYS` | JSON array of JSON keys that should trigger a rejection. |
| `suspicious_json_substrings` | `GEOSYNC_SUSPICIOUS_JSON_SUBSTRINGS` | JSON array of substrings that, when present in JSON values, cause the WAF to reject the request. |
| `upstream_waf_request_id_header` | `GEOSYNC_UPSTREAM_WAF_REQUEST_ID_HEADER` | Header supplied by the external gateway that uniquely identifies the transaction and is copied into audit logs. |
| `upstream_waf_forwarded_for_header` | `GEOSYNC_UPSTREAM_WAF_FORWARDED_FOR_HEADER` | Header from the upstream WAF that contains the canonical client IP chain used for rate limiting. |
| `upstream_waf_event_header` | `GEOSYNC_UPSTREAM_WAF_EVENT_HEADER` | Header carrying the upstream inspection disposition (e.g., allow, challenged) that is recorded in FastAPI security logs. |

### Example: tighten ingress for production

```bash
export GEOSYNC_TRUSTED_HOSTS='["api.geosync.com", "api.geosync.internal"]'
export GEOSYNC_MAX_REQUEST_BYTES=524288
export GEOSYNC_SUSPICIOUS_JSON_KEYS='["$where", "__proto__"]'
export GEOSYNC_SUSPICIOUS_JSON_SUBSTRINGS='["<script", "javascript:"]'
```

Apply the new configuration and verify that your ingress controller forwards the
correct host headers. Requests originating from unlisted hosts or violating the
payload rules will be rejected before reaching any route handlers.

### External gateway integration

GeoSync assumes a managed cloud WAF or API gateway performs TLS termination,
bot mitigation, and deep payload inspection before traffic reaches the
FastAPI runtime. The `upstream_waf_*` settings document how decision metadata
is handed off so the in-app WAF can trust the forwarded context.

1. Require the external gateway to populate the request ID and client IP chain
   headers configured through `GEOSYNC_UPSTREAM_WAF_REQUEST_ID_HEADER` and
   `GEOSYNC_UPSTREAM_WAF_FORWARDED_FOR_HEADER`. The FastAPI WAF relies on
   these values to coordinate quota enforcement and correlate audit entries
   with upstream logs.
2. Propagate the inspection outcome header configured via
   `GEOSYNC_UPSTREAM_WAF_EVENT_HEADER`. Persist the value in application logs
   and forward it to your SIEM so investigations can pivot between gateway and
   application perspectives.
3. Offload full body signature scanning and protocol anomaly detection to the
   cloud WAF while keeping schema-aware JSON validation (key/substring guards)
   inside the application where domain-specific rules are maintained.
4. Stream both the upstream WAF logs and the FastAPI audit trail to a shared
   log aggregation account. Correlate them using the propagated request ID so
   cross-tier investigations remain deterministic.

### Operational checklist

1. Confirm that health checks and reverse proxies use an allowed host header.
2. Roll out stricter payload limits during off-peak hours and monitor error logs
   for false positives.
3. Review suspicious payload patterns regularly and update the JSON guard lists
   as new attack signatures emerge.

## Testing and validation

* Use `pytest tests/api/test_service.py::test_client_rate_limit_is_enforced` to
  validate rate limit policies locally.
* Use `pytest tests/api/test_service.py::test_trusted_host_middleware_blocks_unlisted_hosts`
  and `pytest tests/api/test_service.py::test_payload_guard_rejects_large_and_suspicious_bodies`
  to validate WAF behaviour before promoting changes.
