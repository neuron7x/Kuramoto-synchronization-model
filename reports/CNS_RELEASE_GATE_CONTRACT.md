# CNS Release Gate Contract

This report is intentionally static and small. Dynamic evidence is generated under `results/` by the release-gate tools.

## Required checks

- protocol config validation
- manifest build
- manifest verification
- reports contract validation
- weighted quality decision

## Evidence boundary

Runtime JSON evidence must be regenerated from the current checkout. A stale `results/` directory is not a release witness.

## Non-goals

- no clinical claim
- no psychological diagnosis
- no trading performance claim
- no generated evidence treated as permanent truth
