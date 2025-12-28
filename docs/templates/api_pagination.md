---
owner: platform@tradepulse.example
review_cadence: quarterly
last_reviewed: 2025-02-14
links:
  - docs/api/overview.md
  - docs/documentation_standardisation_playbook.md
---

# API Pagination Patterns

<details>
<summary>How to use this template</summary>

- Specify supported pagination strategies (cursor, offset, time-based).
- Include example requests and responses.
- Document limits, sorting, and filtering interactions.
- Remove this block once the document is complete.

</details>

## Pagination Strategy

Describe the primary pagination strategy and when it applies.

## Request Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| | | | |

## Response Fields

| Field | Type | Description |
| --- | --- | --- |
| | | |

## Examples

```bash
curl "https://api.tradepulse.example/v1/resource?cursor=...&limit=50"
```

```json
{
  "data": [],
  "next_cursor": "",
  "previous_cursor": ""
}
```

## Edge Cases

- Empty page handling
- Maximum page size behavior
- Ordering guarantees

## References

- Link to API reference and client guidance.
