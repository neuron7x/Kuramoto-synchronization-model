---
owner: security@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Policy Decision Contract

This document defines the formal decision contract for MLSdM policy governance.

## 1. Decision Types

The policy system uses five decision types in priority order:

| Priority | Decision | Description |
|----------|----------|-------------|
| 1 (highest) | `BLOCK` | Completely block the action/content. No output produced. |
| 2 | `REDACT` | Allow action but remove/mask sensitive parts. |
| 3 | `REWRITE` | Allow action with modified/sanitized content. |
| 4 | `ESCALATE` | Defer to human/higher authority for decision. |
| 5 (lowest) | `ALLOW` | Permit the action with no modifications. |

## 2. Priority Resolution Rules

When multiple policy modules produce different decisions:

1. **BLOCK wins all**: Any BLOCK decision overrides all others
2. **REDACT over REWRITE/ALLOW**: If any module says REDACT (and none say BLOCK), apply REDACT
3. **REWRITE over ALLOW**: If any module says REWRITE (and none say BLOCK/REDACT), apply REWRITE
4. **ESCALATE behavior**:
   - In `strict_mode=True`: ESCALATE is treated as BLOCK (fail-closed)
   - In `strict_mode=False`: ESCALATE defers to configured escalation handler
5. **ALLOW requires justification**: ALLOW must have at least one reason in the decision trace

## 3. Strict Mode Policy

| Mode | On Exception | On ESCALATE | On Empty Reasons |
|------|--------------|-------------|------------------|
| `strict_mode=True` | BLOCK | BLOCK | BLOCK |
| `strict_mode=False` | Log + ALLOW | Escalate handler | ALLOW with warning |

## 4. Decision Trace Requirements

Every decision MUST include a `DecisionTrace` with:

- `trace_id`: Unique identifier (UUID v4)
- `stage`: Pipeline stage (prefilter/policy/postfilter)
- `input_hash`: SHA256 of normalized input (for reproducibility)
- `module_name`: Module that produced this decision
- `module_version`: Version of the module
- `signals`: Dict of key numeric signals (thresholds, scores)
- `rule_hits`: List of rule identifiers that matched
- `final_decision`: The resolved DecisionType
- `reasons`: Machine-readable reason tags
- `confidence`: Optional confidence score 0.0-1.0
- `redactions`: List of applied redactions (positions, replacement)
- `rewritten_text`: Modified text if REWRITE
- `strict_mode`: Whether strict mode was active
- `created_at`: ISO 8601 timestamp

## 5. Trace Scrubbing

Decision traces MUST NOT contain raw PII or secrets. The trace scrubber:

- Masks email addresses: `user@example.com` → `[EMAIL_REDACTED]`
- Masks phone numbers: `+1-555-123-4567` → `[PHONE_REDACTED]`
- Masks API tokens/keys: Patterns like `sk_live_...`, `Bearer ...` → `[TOKEN_REDACTED]`
- Masks SSN patterns: `123-45-6789` → `[SSN_REDACTED]`
- Masks credit card patterns: `4111-1111-1111-1111` → `[CARD_REDACTED]`

## 6. Red-Team Validation

Policy decisions are validated against adversarial test cases:

- **Prompt injection**: Attempts to override system prompts
- **Jailbreak**: Attempts to bypass safety guidelines
- **Data exfiltration**: Attempts to extract sensitive data
- **Policy evasion**: Obfuscated attempts to bypass rules
- **Harmful content**: Violence, self-harm, malware (detection only)
- **Data leakage**: Accidental exposure of PII/secrets

Each test case specifies `expected_minimum_decision` - the weakest acceptable response.
For example, `expected_minimum_decision=REDACT` means REDACT, BLOCK, or ESCALATE are acceptable, but ALLOW or REWRITE are failures.

## 7. Backward Compatibility

New decision types are additive. Existing consumers that only understand GO/HOLD/NO_GO:

- `ALLOW` maps to `GO`
- `BLOCK` maps to `NO_GO`
- `REDACT`, `REWRITE`, `ESCALATE` map to `HOLD`

## 8. Example Decision Trace JSON

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "stage": "policy",
  "input_hash": "sha256:a1b2c3d4...",
  "module_name": "threat_prefilter",
  "module_version": "1.2.0",
  "signals": {
    "threat_score": 0.85,
    "threshold": 0.7
  },
  "rule_hits": ["injection_pattern_001", "suspicious_encoding"],
  "final_decision": "BLOCK",
  "reasons": ["threat_score_exceeded", "injection_detected"],
  "confidence": 0.92,
  "redactions": [],
  "rewritten_text": null,
  "strict_mode": true,
  "created_at": "2025-12-16T18:00:00Z"
}
```
