---
owner: platform@tradepulse.example
review_cadence: quarterly
last_reviewed: 2025-02-14
links:
  - docs/api/overview.md
  - docs/documentation_standardisation_playbook.md
---

# API Rate Limits & Quotas

<details>
<summary>How to use this template</summary>

- Document per-route and per-tenant limits.
- Include response headers and retry-after behavior.
- Provide quota reset cadence and burst handling.
- Remove this block once the document is complete.

</details>

## Rate Limit Policy

| Scope | Limit | Window | Burst | Notes |
| --- | --- | --- | --- | --- |
| | | | | |

## Response Headers

List headers such as `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After`.

## Throttling Behavior

Describe soft vs hard throttles and expected client behavior.

## Monitoring & Alerts

- Metrics to monitor
- Alert thresholds

## References

- Link to API reference and operational runbooks.
