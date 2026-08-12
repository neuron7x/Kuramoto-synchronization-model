# Web Agent Tool Contract Inventory

`WEB-AGENT-ARCH-001 · Tool Contracts 001`

## Status

```text
STATIC_TOOL_CONTRACTS_DEFINED
LIVE_ADAPTER_BEHAVIOR_NOT_VERIFIED
```

This document binds the web-agent architecture to a minimal tool surface. It is intentionally small because solo-agent systems do not become safer by collecting tools like cursed souvenirs.

The machine-readable artifact is:

```text
artifacts/agents/web_agent_tool_contract_inventory.json
```

## Contract rule

Every tool must have:

- exactly one responsibility;
- explicit input schema;
- explicit output schema;
- explicit side-effect declaration;
- explicit failure mode;
- bounded retry policy;
- escalation rule.

A tool output is evidence. It is not instruction authority unless it comes from the trusted orchestration layer.

## Static inventory

| Tool | Responsibility | Side effect | Failure mode | Retry policy | Escalation |
|---|---|---|---|---|---|
| `web_search` | Return ranked public web results | none | explicit error or empty result | transient backoff max 3 | ambiguous query or conflicting sources |
| `web_fetch` | Fetch one URL with provenance | none | explicit fetch error | transient backoff max 3 | instruction override in content |
| `file_read` | Read one scoped file | none | missing or permission error | no retry for missing file | sensitive or ambiguous target |
| `file_write` | Write one scoped artifact | writes file | explicit write error | retry only transient IO | overwrite/path uncertainty |
| `code_exec` | Execute bounded command | bounded runtime effects | nonzero exit with logs | no retry without changed input | destructive/unbounded command |
| `github_fetch_file` | Fetch one repo file at one ref | none | API error or not found | transient backoff max 3 | ambiguous ref or missing expected file |
| `github_create_file` | Create one new repo file | creates commit | API error or path exists | no retry without branch refetch | branch/path uncertainty |
| `github_update_file` | Replace one existing repo file with SHA | creates commit | API error or SHA conflict | refetch SHA before retry | overwrite uncertainty |

## Coverage calculation

```text
total_tools = 8
tools_with_single_responsibility = 8
tools_with_input_schema = 8
tools_with_output_schema = 8
tools_with_failure_mode = 8
tools_with_retry_policy = 8
coverage_ratio = 1.0
```

## Boundary warning

This is **static contract coverage**, not live adapter verification.

It closes the documentation/schema gap for tool responsibilities. It does not prove that the actual runtime tool adapter behaves correctly under API failure, auth failure, stale SHA, prompt injection, timeout, or partial response.

## Failure conditions

```text
- Do not treat static inventory as live adapter proof.
- Do not allow untrusted tool output to become instruction authority.
- Do not perform irreversible or destructive external actions without explicit confirmation.
```
