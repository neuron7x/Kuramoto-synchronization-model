---
owner: integrations@tradepulse
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/integration-api.md
  - docs/documentation_standardisation_playbook.md
---

# API Contract: <Service Name>

<details>
<summary>How to use this template</summary>

- Pair this contract with machine-readable schemas (OpenAPI, Protobuf) stored
  under `schemas/` or `api/` directories.
- Document versioning, backward compatibility, and SLA expectations.
- Include example requests/responses with redacted sensitive data.
- Remove this block before publishing.

</details>

## Overview

- **Service Owner:**
- **Protocol(s):** REST/gRPC/WebSocket
- **Authentication:**
- **Rate Limits:**

## Versioning

- **Current Version:** vX.Y
- **Release Date:**
- **Change Log:** Link to release notes or ADR.

## Endpoints / Methods

| Endpoint | Method | Description | Request Schema | Response Schema | Idempotency |
| -------- | ------ | ----------- | -------------- | --------------- | ----------- |
| `/path` | GET | | `schemas/<request>.proto` | `schemas/<response>.proto` | Yes/No |

## Error Handling

| Code | Type | Description | Retry Guidance |
| ---- | ---- | ----------- | -------------- |
| 429 | RateLimitExceeded | Too many requests | Retry-After header |

## Example

```http
GET /path HTTP/1.1
Host: api.tradepulse.example
Authorization: Bearer <token>
```

```json
{
  "field": "value"
}
```

## Observability

- **Metrics:**
- **Logs:**
- **Tracing Spans:**

## Compliance & Data Handling

- **PII Classification:**
- **Retention:**
- **Data Residency:**

## Changelog

| Date | Version | Author | Notes |
| ---- | ------- | ------ | ----- |
| 2025-12-28 | v1.1 | Docs Guild | Reviewed template metadata and refreshed module alignment references. |
| YYYY-MM-DD | vX.Y | name | Initial draft |
