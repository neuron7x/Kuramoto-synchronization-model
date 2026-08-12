<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Operator: Integrate

## Definition

**Integrate** means to connect separate modules or services into one coherent system through explicit contracts, validated boundaries, and observable runtime behavior.

Ukrainian operational definition:

```text
Інтегрувати — об'єднати модулі або сервіси в єдину систему так, щоб кожен компонент мав визначену роль, вхід, вихід, контракт, перевірку та відмову без прихованої магії.
```

## Operator Form

```text
input_modules + interface_contracts + validation_gates
→ integration_operation
→ coherent_system + evidence_bundle + rollback_path
```

## Purpose

Integration is not file aggregation. Integration is the controlled reduction of system entropy by making independent parts communicate through stable interfaces.

## Required Inputs

```text
modules_or_services
owned_interfaces
input_output_contracts
dependency_reasons
validation_commands
failure_modes
rollback_plan
```

## Required Outputs

```text
system_boundary
module_map
integration_contract
dependency_graph
smoke_path
validation_report
rollback_path
```

## Acceptance Gates

```text
No module without a purpose.
No service without an owner interface.
No dependency without a reason.
No interface without input/output contract.
No integration without at least one smoke command.
No PASS without persisted evidence.
```

## Failure Modes

```text
components are colocated but not integrated
shared state appears without ownership
service boundary is unclear
module import path works only locally
CLI path bypasses API contract
API path bypasses validation
integration creates hidden dependency cycles
rollback cannot restore previous behavior
```

## Status Discipline

```text
S0_REPO_FACT   operator spec exists in repo
S1_TESTED      validator and smoke paths have executed successfully
S5_PROXY       integration quality is measured through operational heuristics
```

Until commands are executed and evidence is persisted, this operator remains `S0_REPO_FACT + S5_PROXY`, not `S1_TESTED`.

## Minimal Validation

```bash
python tools/research/validate_operator_contract.py docs/operators/integrate_operator.json
python -m pytest tests/research/test_integrate_operator_contract.py -q
```

## Next Integration Target

Bind this operator to a real GeoSync/CME path:

```text
CLI command → service function → schema contract → evidence artifact → verdict file
```

That path is the first real integration surface. Anything else is just modules standing near each other, which apparently passes for architecture if nobody is watching.
