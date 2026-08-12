# SignalBus Theory Boundary

## Scope

This contract covers deterministic signal propagation in the NeuroSignalBus layer.

## Model

For acyclic subscriber graphs, one root publish defines one deterministic fanout traversal. Each subscribed callback in the reachable DAG must fire exactly once, and downstream publishes must be visible in the final snapshot.

## Invariants

- INV-SB1: acyclic fanout fires every reachable subscriber exactly once per root publish.
- INV-SB2: replaying the same publish sequence into fresh bus instances yields identical snapshots.

## Witness rules

Tests must declare the subscriber graph shape, root channel, payloads, and expected callback counts. Acyclic traversal witnesses must not claim that the bus prevents cycles unless a cycle detector exists.

## Boundary

The current invariant is a DAG-correctness claim, not a general scheduler, concurrency, or cycle-rejection proof. Cyclic subscriptions are outside the promoted evidence boundary unless a fail-closed cycle guard is implemented and tested.
