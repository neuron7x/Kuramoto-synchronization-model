# Execution instructions
- Execution actions must be idempotent when retried.
- Classify retries by error type and exchange semantics.
- Enforce timeout and cancellation policy (cancel/replace where applicable).
- Reject stale quotes/events and keep default behavior deny-safe.
