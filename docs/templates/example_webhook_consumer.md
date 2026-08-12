---
owner: dx@geosync
review_cadence: quarterly
last_reviewed: 2025-02-14
links:
  - docs/examples/README.md
  - docs/documentation_standardisation_playbook.md
---

# Example: Webhook Consumer

<details>
<summary>How to use this template</summary>

- Use for webhook verification and retry handling examples.
- Include signature validation and replay protection.
- Show sample payloads and expected responses.
- Remove this block once the example is complete.

</details>

## Objective

Explain the webhook event handled and expected outcomes.

## Prerequisites

- Public webhook endpoint
- Shared secrets or public keys
- Logging/monitoring setup

## Handler Flow

1. Receive event
2. Validate signature and timestamp
3. Persist or act on payload
4. Respond with success

## Sample Payload

```json
{
  "event": "",
  "data": {}
}
```

## Verification Steps

- Expected HTTP status
- Replay attack checks

## Troubleshooting

List common errors and fixes.
