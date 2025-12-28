---
owner: platform@tradepulse.example
review_cadence: quarterly
last_reviewed: 2025-02-14
links:
  - docs/api/overview.md
  - docs/documentation_standardisation_playbook.md
---

# API Error Model

<details>
<summary>How to use this template</summary>

- Capture the error envelope schema and field definitions.
- Provide a catalog of common error codes and retry guidance.
- Include examples for both client and server errors.
- Remove this block once the document is complete.

</details>

## Error Envelope

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "request_id": "string",
    "details": {}
  }
}
```

## Error Code Catalog

| Code | HTTP Status | Category | Description | Retry? |
| --- | --- | --- | --- | --- |
| | | | | |

## Retry & Backoff Guidance

- Default retry policy
- Idempotency considerations
- Rate-limit retry strategy

## Examples

```json
{
  "error": {
    "code": "",
    "message": "",
    "request_id": "",
    "details": {}
  }
}
```

## References

- Link to API reference, SLA, and incident playbooks.
