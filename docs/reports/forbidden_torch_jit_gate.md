# Forbidden torch JIT / deserialization gate (P0-3)

Status: ACTIVE
Owner: security
Gate: `tools/security/check_forbidden_torch_jit.py`
Commit acceptor: `.claude/commit_acceptors/p03-torch-jit-gate.yaml`

## Why this exists

A historical dependency advisory against `torch` was dismissed on the basis
that the repository's TorchScript JIT and arbitrary-pickle deserialization
paths are **unused**. That is a load-bearing assumption for the dismissal, and
an assumption is not a control. P0-3 converts the assumption into an enforced,
fail-closed invariant: any reintroduction of a forbidden API breaks CI.

## What is forbidden

| API                | Disposition                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| `torch.jit.script` | forbidden (compiles arbitrary Python into TorchScript)                      |
| `torch.jit.trace`  | forbidden (traces arbitrary Python into TorchScript)                        |
| `torch.jit.load`   | forbidden (deserializes a TorchScript code+tensor archive)                  |
| `torch.load`       | forbidden **unless** called with the literal keyword `weights_only=True`    |

`torch.load(..., weights_only=True)` restricts the unpickler to tensor storages
and rejects arbitrary object reconstruction, so it is the only permitted
deserialization form. A non-literal `weights_only` value (a variable or
expression) is treated as *unguarded* — the gate demands a statically provable
`True` so the untrusted path cannot be re-enabled at runtime.

## How detection works

Detection is **AST-based**, not regex-based. The scanner:

- resolves attribute chains (`torch.jit.script`);
- resolves import aliases — `import torch.jit as J; J.script(...)` and
  `from torch.jit import load as L; L(...)` both resolve to their true torch
  target, so aliasing cannot smuggle a forbidden call past the gate;
- never inspects comments or string literals, so prose naming a forbidden
  symbol (including this document) does not trip the gate.

The gate excludes itself and its own test fixtures (which construct forbidden
calls on purpose to prove detection works) via an exact relpath exemption list.

## Allowlist

A legitimately guarded use may be exempted by an exact `path::line::api` triple
in `tools/security/forbidden_torch_jit_allowlist.json`. The allowlist:

- cannot exempt a whole file or an API globally — only a precise source line;
- requires a non-empty human `reason` per entry (schema-validated);
- is currently **empty** — the repository has no use that needs an exemption.

## Repo-wide scan result (current main)

```
forbidden-torch-jit gate: scanned 3569 python file(s); 0 unreviewed finding(s), 0 allowlisted.
```

Exit code 0. The four production `torch.load` call sites
(`geosync_unified.py`, `geosync_hydro/monitor.py`, `geosync_hydro/utils.py`,
`strategies/quantum_neural.py`) all pass the literal `weights_only=True` and are
therefore clean. There is no `torch.jit.{script,trace,load}` usage anywhere.

## Run locally

```bash
python tools/security/check_forbidden_torch_jit.py            # exit 0 on clean repo
pytest -q tests/tools/test_forbidden_torch_jit.py             # gate unit + repo-wide tests
```

## Relationship to existing controls

`tests/security/test_checkpoint_loading.py` asserts the two `geosync_*`
checkpoint loaders pass `weights_only=True` at runtime (behavioural). This gate
is the complementary **repo-wide static** invariant: it covers every call site
and every forbidden JIT API, so a new unguarded sink anywhere in the tree fails
CI even if no behavioural test exercises it.
