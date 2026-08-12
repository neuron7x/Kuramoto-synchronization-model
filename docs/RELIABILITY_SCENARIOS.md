# Reliability Scenarios: Golden Path Failure Modes

> **Purpose**: Document canonical failure scenarios for GeoSync's golden path (backtest workflow and minimal live trading cycle) with explicit reproduction steps and expected behavior.
>
> **Last Updated**: 2025-12-11
> **Maintainer**: GeoSync Team

## Overview

This document defines the key failure modes for GeoSync's core workflows and validates that the system fails gracefully without data corruption, silent errors, or zombie processes. Each scenario is backed by automated tests in `tests/reliability/`.

### Goals

1. **Controlled Failure**: System must fail with clear error messages and appropriate exit codes
2. **No Data Corruption**: Intermediate artifacts must be either complete or cleanly absent
3. **Fast Recovery**: Errors must be detected quickly (no hanging processes)
4. **Observable**: Failures must be logged with actionable information

### Non-Goals

- High availability / automatic failover (covered in production ops docs)
- Performance degradation scenarios (covered in performance testing)
- Security exploits (covered in security testing)

---

## Failure Scenarios Registry

| id | scenario | command_to_reproduce | expected_behavior | status | notes |
|----|----------|---------------------|-------------------|--------|-------|
| REL_BACKTEST_CRASH_001 | Exception in core backtest engine mid-run | `pytest tests/reliability/test_backtest_crash_handling.py::test_strategy_exception_handling -v` | Backtest terminates with non-zero exit code, exception is logged with context, no partial artifacts written | proven | Validates exception propagation through engine |
| REL_BACKTEST_CRASH_002 | Unhandled exception in strategy callback | `pytest tests/reliability/test_backtest_crash_handling.py::test_strategy_callback_crash -v` | Engine catches exception, includes strategy context in error, returns structured failure result | proven | Protects engine from user code errors |
| REL_DATA_MISSING_001 | Missing price data (NaN values) in input | `pytest tests/reliability/test_missing_market_data.py::test_nan_price_detection -v` | Data validation fails before backtest starts, clear error identifying which symbols/dates have NaN | proven | Pre-flight validation prevents garbage in/out |
| REL_DATA_MISSING_002 | Gaps in timestamp sequence | `pytest tests/reliability/test_missing_market_data.py::test_timestamp_gap_detection -v` | Validation reports gaps with specific timestamps, backtest refuses to proceed unless gaps are explicitly allowed | proven | Protects against time-series integrity issues |
| REL_DATA_MISSING_003 | Completely empty dataset | `pytest tests/reliability/test_missing_market_data.py::test_empty_dataset_handling -v` | Clear error message indicating no data available, suggests checking data source configuration | proven | Common misconfiguration scenario |
| REL_EXEC_TIMEOUT_001 | Execution adapter timeout (slow broker API) | `pytest tests/reliability/test_execution_adapter_failures.py::test_order_timeout_handling -v` | Order marked as timed out, no silent hang, timeout error logged with duration | proven | Prevents infinite waits on external systems |
| REL_EXEC_TIMEOUT_002 | Connection failure to broker | `pytest tests/reliability/test_execution_adapter_failures.py::test_connection_failure_handling -v` | Connection error caught, retries exhaust quickly, clear error message with broker details | proven | Validates error handling for network issues |
| REL_EXEC_TIMEOUT_003 | Partial fills with timeout | `pytest tests/reliability/test_execution_adapter_failures.py::test_partial_fill_tracking -v` | System tracks partial fill accurately, does not assume full execution, logs partial state | proven | Prevents position tracking corruption |
| REL_CONFIG_INVALID_001 | Malformed YAML configuration | `pytest tests/reliability/test_invalid_config.py::test_yaml_parse_error -v` | Parse error with line number, no stack trace spam, suggests fix | proven | Common user error scenario |
| REL_CONFIG_INVALID_002 | Missing required configuration fields | `pytest tests/reliability/test_invalid_config.py::test_missing_required_fields -v` | Validation lists all missing fields, clear error message | proven | Fail-fast on incomplete config |
| REL_CONFIG_INVALID_003 | Invalid value types (string where number expected) | `pytest tests/reliability/test_invalid_config.py::test_type_validation -v` | Type error with field name and expected type, actual value shown | proven | Schema validation catches type mismatches |
| REL_CONFIG_INVALID_004 | Incompatible parameter combinations | `pytest tests/reliability/test_invalid_config.py::test_incompatible_parameters -v` | Semantic validation error explaining incompatibility, suggests valid combinations | proven | Cross-field validation prevents contradictory configs |
| REL_PROCESS_INT_001 | Graceful shutdown on SIGTERM | `pytest tests/reliability/test_process_interruption.py::test_sigterm_graceful_shutdown -v` | Process cleans up resources, writes checkpoint, exits with code 0 within timeout | partial | Basic signal handling tested, checkpoint logic simplified |

---

## Scenario Details

### REL_BACKTEST_CRASH_001: Exception in Backtest Engine

**Description**: Internal exception occurs during backtest execution (e.g., division by zero in performance calculation).

**Reproduction**:
```bash
pytest tests/reliability/test_backtest_crash_handling.py::test_strategy_exception_handling -v
```

**Expected Behavior**:
- Process exits with non-zero code (not 0)
- Exception logged with full stack trace and context
- No partial output files written (or marked as incomplete)
- Error message includes timestamp, strategy name, and bar index

**What NOT to do**:
- Silent failures (returning success when error occurred)
- Hanging indefinitely waiting for recovery
- Writing corrupt artifacts that look valid
- Generic "something went wrong" without context

---

### REL_DATA_MISSING_001: NaN Values in Price Data

**Description**: Input price data contains NaN values due to data quality issues.

**Reproduction**:
```bash
pytest tests/reliability/test_missing_market_data.py::test_nan_price_detection -v
```

**Expected Behavior**:
- Pre-flight validation catches NaN before backtest starts
- Error message specifies: symbol, date range, which field (open/close/high/low)
- Backtest refuses to run
- Suggests data quality checks or gap-filling strategies

**What NOT to do**:
- Silently skip NaN bars (leads to unrealistic results)
- Propagate NaN through calculations (corrupts metrics)
- Allow backtest to start then fail mid-run

---

### REL_EXEC_TIMEOUT_001: Order Timeout

**Description**: Execution adapter times out waiting for broker order acknowledgement.

**Reproduction**:
```bash
pytest tests/reliability/test_execution_adapter_failures.py::test_partial_fill_tracking -v
```

**Expected Behavior**:
- Order marked with `TIMEOUT` status after configured timeout (e.g., 5s)
- Timeout duration logged
- No assumption that order executed
- System continues with next order (or halts if critical)

**What NOT to do**:
- Wait indefinitely (no timeout configured)
- Assume order succeeded and update position
- Crash the entire system on one timeout
- Retry infinitely without backoff

---

### REL_CONFIG_INVALID_001: Malformed YAML

**Description**: Configuration file has invalid YAML syntax.

**Reproduction**:
```bash
pytest tests/reliability/test_invalid_config.py::test_yaml_parse_error -v
```

**Expected Behavior**:
- YAML parser error with line/column number
- Clear message: "Configuration file is invalid YAML"
- Suggests checking syntax with YAML validator
- No deep Python stack traces shown to user

**What NOT to do**:
- Generic "config error" without location
- Attempt to partially parse and guess intent
- Start with default config silently

---

## Test Execution Guide

### Run All Reliability Tests

```bash
pytest tests/reliability/ -v
```

Expected runtime: < 30 seconds (all tests are fast, no network I/O)

### Run Specific Scenario

```bash
pytest tests/reliability/test_backtest_crash_handling.py -v
pytest tests/reliability/test_missing_market_data.py -v
pytest tests/reliability/test_execution_adapter_failures.py -v
pytest tests/reliability/test_invalid_config.py -v
```

### Run in CI

Tests are automatically executed in `.github/workflows/reliability-smoke.yml` on every PR.

---

## Maintenance

1. **Add new scenarios** when:
   - Production incidents reveal new failure modes
   - New components added to golden path
   - User reports unexpected error behavior

2. **Update existing scenarios** when:
   - Error message format changes
   - Timeout values adjusted
   - Validation logic enhanced

3. **Archive scenarios** when:
   - Component removed from golden path
   - Failure mode no longer possible (architectural change)

---

## Integration with Other Docs

- **METRICS_CONTRACT.md**: Reliability claims reference these scenarios as evidence
- **README.md**: Links to this document for reliability transparency
- **INCIDENT_RUNBOOK.md**: Production failures cross-reference scenario IDs
- **TESTING.md**: Test architecture explains reliability test structure

---

## Status Legend

| Status | Meaning |
|--------|---------|
| `proven` | Test exists, passes in CI, covers scenario |
| `partial` | Test exists but incomplete or not in CI |
| `goal` | Planned but not yet implemented |
| `deprecated` | Scenario no longer relevant |

---

**⚠️ NOTE**: These tests validate graceful failure, not failure prevention. They ensure the system "fails well" when errors occur, not that errors never occur.
