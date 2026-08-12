# Web Agent Operationalization Matrix

`WEB-AGENT-ARCH-001 · Operationalization Layer`

## Executive verdict

Status: `CONTROL_PLANE_DEFINED_NOT_BASELINED`

The protocol is operationalized when every abstract rule is mapped to an owner role, resource, metric, checkpoint, and failure condition.

This file converts the architecture protocol into an execution matrix. It does not claim production readiness.

## Roles

| Role ID | Role | Responsibility | Escalates when |
|---|---|---|---|
| R0 | Orchestrator | Owns task decomposition and action authorization | uncertainty is high or effect is irreversible |
| R1 | Context Engineer | Controls context load, compaction, retrieval boundaries | context grows without measurable utility |
| R2 | Tool Architect | Defines atomic tool contracts | tool does multiple responsibilities |
| R3 | Security Critic | Tests prompt injection and trust-zone boundaries | untrusted content attempts instruction override |
| R4 | Error-State Engineer | Defines retry, fallback, ambiguity, and hard-stop paths | failure mode is unknown |
| R5 | Metrics Auditor | Defines baseline values and measurement functions | metric cannot be computed |
| R6 | Memory Steward | Controls working, episodic, and semantic memory boundaries | state is persisted without need |
| R7 | Release Gatekeeper | Blocks production readiness claims | any acceptance gate is open |

## Resources

| Resource ID | File / artifact | Purpose |
|---|---|---|
| RES-001 | `docs/agents/WEB_AGENT_ARCHITECTURE_PROTOCOL.md` | Canonical architecture protocol |
| RES-002 | `docs/agents/web_agent_operationalization_matrix.md` | Execution matrix |
| RES-003 | `schemas/web_agent_score.schema.json` | Machine-readable metric schema |
| RES-004 | `tests/agents/test_web_agent_protocol_contract.py` | Smoke contract test |
| RES-005 | `artifacts/agents/baseline_score.json` | Future measured baseline artifact |
| RES-006 | `docs/agents/prompt_injection_test_plan.md` | Future adversarial test plan |
| RES-007 | `docs/agents/tool_contracts.md` | Future tool-level interface contracts |
| RES-008 | `docs/agents/memory_policy.md` | Future memory persistence policy |
| RES-009 | `VERDICT.md` | Final release state |

## Metrics

| Metric ID | Metric | Formula / measurement | Target | Failure condition |
|---|---|---|---|---|
| M001 | task_completion_rate | correctly completed tasks / total tasks | >= 0.95 | unresolved task marked done |
| M002 | irreversible_action_violations | irreversible actions without confirmation | 0 | any unconfirmed irreversible write |
| M003 | context_efficiency | tokens_used / estimated_required_tokens | <= 1.30 | context dump without retrieval need |
| M004 | hallucination_rate | unsupported claims / total claims | <= 0.02 | claim lacks source or artifact |
| M005 | escalation_precision | correct escalations / all escalations | >= 0.90 | agent asks when deterministic action was safe or acts when it should ask |
| M006 | injection_resistance | pass/fail adversarial prompt injection suite | true | untrusted content changes trusted behavior |
| M007 | tool_contract_coverage | tools with schema + failure mode / all tools | 1.0 | tool lacks schema or error contract |
| M008 | retry_budget_compliance | retries within policy / retry events | 1.0 | infinite or silent retry loop |
| M009 | memory_minimization | persisted fields required for next step / persisted fields | 1.0 | unnecessary persistence |
| M010 | explanation_completeness | decisions with reason trace / decisions | >= 0.95 | action cannot be explained |

## Checkpoints

| Checkpoint | Owner | Required action | Resource | Metric | Gate |
|---|---|---|---|---|---|
| CP0 Protocol Canonicalization | R0 | Commit canonical protocol | RES-001 | M010 | document exists and has failure conditions |
| CP1 Context Boundary | R1 | Define context compaction rules | RES-001, RES-008 | M003 | context rule has measurable failure condition |
| CP2 Tool Boundary | R2 | Define one-responsibility tool contracts | RES-007 | M007 | every tool has input/output/error schema |
| CP3 Security Boundary | R3 | Define trust-zone and injection tests | RES-006 | M006 | untrusted content cannot override agent behavior |
| CP4 Error Boundary | R4 | Define retry/fallback/ambiguity/hard-stop paths | RES-001 | M008 | retry budget and hard-stop states exist |
| CP5 Metrics Baseline | R5 | Generate baseline score artifact | RES-003, RES-005 | M001-M010 | every metric has baseline value |
| CP6 Memory Boundary | R6 | Define persistence minimization policy | RES-008 | M009 | persisted state is justified |
| CP7 Release Verdict | R7 | Produce PASS/FAIL verdict | RES-009 | all | no open gate before production claim |

## Action sequence

| Rank | Action | Why first | Output | Stop condition |
|---|---|---|---|---|
| 1 | Commit protocol | Establishes canonical behavior contract | RES-001 | protocol missing failure conditions |
| 2 | Add operational matrix | Converts principles into execution gates | RES-002 | role/resource/metric absent |
| 3 | Add score schema | Makes readiness machine-checkable | RES-003 | metric lacks type/threshold |
| 4 | Add smoke contract test | Prevents accidental deletion or hollow protocol | RES-004 | required documents missing |
| 5 | Build tool contracts | Makes external actions deterministic | RES-007 | tool has mixed responsibility |
| 6 | Build injection suite | Tests hostile web content behavior | RES-006 | untrusted text changes instructions |
| 7 | Generate baseline | Replaces opinion with measurement | RES-005 | metric cannot compute |
| 8 | Release verdict | Blocks premature production label | RES-009 | any gate open |

## Production readiness rule

```text
PRODUCTION_READY = all checkpoints CP0..CP7 pass
```

Current state:

```text
CP0: PASS
CP1: PARTIAL
CP2: NOT_STARTED
CP3: NOT_STARTED
CP4: PARTIAL
CP5: NOT_STARTED
CP6: NOT_STARTED
CP7: NOT_STARTED

OVERALL: NOT_PRODUCTION_READY
```

## Do-not-proceed conditions

Stop if:

```text
- metric has no baseline
- tool has no schema
- untrusted content is treated as instruction
- irreversible action lacks confirmation
- memory writes persist unnecessary data
- context grows without compaction
- release verdict is generated without executed tests
```
