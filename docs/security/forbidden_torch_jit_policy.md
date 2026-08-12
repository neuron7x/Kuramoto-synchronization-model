# Forbidden torch JIT / deserialization policy

Fail-closed control enforcing that the repository never exercises the
TorchScript JIT or an unguarded pickle-deserialization path — the assumption on
which a `torch` dependency advisory was dismissed.

- **Gate**: `tools/security/check_forbidden_torch_jit.py`
- **Allowlist**: `tools/security/forbidden_torch_jit_allowlist.json`
- **Tests**: `tests/tools/test_forbidden_torch_jit.py`
- **Report**: `docs/reports/forbidden_torch_jit_gate.md`
- **CI**: `.github/workflows/forbidden-torch-jit-gate.yml`

## Forbidden APIs

- `torch.jit.script`, `torch.jit.trace`, `torch.jit.load` — unconditionally
  forbidden (TorchScript code-archive surface).
- `torch.load` — forbidden **unless** called with the literal keyword
  `weights_only=True`. A non-literal `weights_only` value is treated as
  unguarded.

## Detection

AST-based, alias-aware (resolves `import torch.jit as J` and
`from torch import load as tl`). Comments and string literals are never
inspected. The gate excludes itself and its own test fixtures.

## Exceptions

A legitimately guarded use is exempted only by an exact `path::line::api` entry
with a non-empty `reason` in the allowlist JSON. No file-wide or API-wide
exemptions are possible. Review each addition as a security change.

## Run

```bash
python tools/security/check_forbidden_torch_jit.py
pytest -q tests/tools/test_forbidden_torch_jit.py
```
