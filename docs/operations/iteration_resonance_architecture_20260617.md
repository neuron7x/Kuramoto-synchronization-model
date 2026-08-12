# Iteration Resonance Architecture

## Status

Normative coordination layer for PR #1157.

This document defines how an agent must iterate: not by repeating work mechanically, but by cycling through assessment, intervention, measurement, correction, and stability promotion until the repository reaches a declared stability criterion.

## 1. Core Thesis

Iteration is not repetition.

Iteration is controlled resonance between intent, evidence, runtime behavior, and repository state.

A valid iteration must reduce uncertainty, narrow the defect surface, or raise the confidence level of an already patched system.

An invalid iteration merely produces more commits, more logs, more reports, or more apparent progress without changing the verified state of the system.

## 2. Iteration Loop

Every agent cycle must follow this sequence:

1. assess current observable state;
2. identify the smallest meaningful intervention;
3. apply one bounded change;
4. measure behavior through executable evidence;
5. compare result against the stability criterion;
6. correct only the observed deviation;
7. promote the lane only if the measurement is stable;
8. record the effect in the ledger or scorecard.

The loop is forbidden from starting a new intervention before the previous one has produced a measured result.

## 3. Stability Criterion

A result is stable only when all required conditions hold:

- the same head SHA has completed its required CI gates;
- required tests collected non-zero executable nodeids;
- no critical gate is stale, skipped, or vacuous;
- the relevant metric is PASS, not UNKNOWN;
- the falsifier remains active after the patch;
- the ledger reflects the current state;
- no dependent PR relies on a superseded measurement;
- no local-only result is treated as CI evidence;
- residual risk is explicitly classified.

If any condition is missing, the result is not stable.

## 4. Resonance Levels

### L0: Local Patch Resonance

The patch changes the intended local behavior and has a direct witness.

Promotion rule:
local witness exists, but no merge decision is allowed.

### L1: Lane Resonance

The PR lane passes its own required checks on the same head SHA.

Promotion rule:
PR may become merge-candidate only if its metrics are current.

### L2: Cross-PR Resonance

The PR does not invalidate, duplicate, or stale another active lane.

Promotion rule:
merge order is safe only if dependency and collision checks are clean.

### L3: Repository Resonance

The repository state, CI oracle, ledger, and scorecard agree.

Promotion rule:
closure may be recorded only if the state is globally consistent.

### L4: Structural Resonance

The defect class becomes harder or impossible to reintroduce because the architecture, tests, acceptors, and metrics reject it.

Promotion rule:
final closure may be claimed only at this level.

## 5. Agent Behavior Requirements

The agent must behave as follows:

- one iteration, one measured uncertainty reduction;
- one patch, one defect class;
- one claim, one witness;
- one resolved state, one resolution reference;
- one metric, one source of truth;
- no merge from stale evidence;
- no confidence from repeated reports;
- no closure from local-only proof;
- no green from zero exercised behavior;
- no scorecard PASS above the weakest required metric.

## 6. Escalation Logic

The agent must escalate the frame when repetition no longer reduces uncertainty.

Escalation triggers:

- the same failure repeats after two bounded patches;
- a PR passes locally but fails in CI;
- a metric remains UNKNOWN after measurement;
- a lane is green but depends on a stale oracle;
- backlog shape grows beyond the current PR scope;
- a patch fixes a symptom but not the defect class;
- a closure claim lacks ledger alignment.

Escalation actions:

- move from local patch to lane-level diagnosis;
- move from lane diagnosis to cross-PR collision analysis;
- move from cross-PR analysis to repository-level quarantine;
- move from quarantine to scorecard only after explicit ownership exists.

## 7. Correction Rules

Correction must be proportional to evidence.

Allowed corrections:

- fix the directly observed failing path;
- strengthen the falsifier;
- add a missing witness;
- update stale ledger state;
- bound a claim that exceeded evidence;
- quarantine known backlog with explicit ownership.

Forbidden corrections:

- broad refactor to avoid a narrow failure;
- hiding failures behind skip logic;
- weakening tests to restore green;
- merging a red oracle as if it were a feature;
- opening a new PR to escape the current blocker;
- declaring stability from a single unverified local run.

## 8. Iteration Metrics

Each iteration must report:

- uncertainty_reduced: yes or no;
- defect_class_addressed;
- evidence_source;
- measurement_result;
- repeated_failure_count;
- new_failure_surface;
- residual_risk;
- promotion_level: L0, L1, L2, L3, or L4;
- stop_condition_met: yes or no.

If uncertainty_reduced is no, the agent must stop and reframe.

## 9. Stop Rules

Stop immediately when:

- the next action would broaden scope without evidence;
- the measurement source is invalid;
- the same failure persists without new information;
- the agent cannot identify the owner of the next intervention;
- a required source of truth is unavailable;
- the PR would merge from stale or vacuous evidence.

Stopping is not failure.

Stopping is valid control when the system lacks enough evidence to continue safely.

## 10. Final Iteration Contract

A lane may be called complete only when it reaches at least L3.

A defect class may be called structurally closed only when it reaches L4.

A scorecard may call PASS only when all required lanes are at L3 or higher and all structural blockers are either L4 or explicitly quarantined with owner, reason, and expiry condition.

## 11. Final Output Schema

After each iteration, the agent must return:

repo_state:
active_pr:
iteration_number:
promotion_level:
intent:
intervention:
measurement:
correction:
uncertainty_reduced:
defect_class_addressed:
evidence_source:
residual_risk:
stop_condition_met:
next_frame:
verdict:
