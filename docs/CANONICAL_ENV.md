# Canonical Python 3.12 Environment (ENV-001)

ENV-001 defines and verifies the **canonical Python 3.12 environment descriptor**
and a **fail-closed preflight gate**. It is the gatekeeper for the TST / ARC / PKG
waves: nothing downstream should run against an interpreter that fails this gate.

> **Scope boundary (be honest).** ENV-001 is the *descriptor + preflight*, **not**
> the hermetic container. Building a reproducible, hash-locked, floor-satisfying
> container image is **ENV-005**. This document records exactly where the current
> execution sandbox differs from that ideal.

## Artifacts

| Artifact | Purpose |
| --- | --- |
| `scripts/ci/check_env_preflight.py` | Fail-closed preflight gate + descriptor emitter. |
| `tests/ci/test_env_preflight.py` | Positive (real env passes) + negative (fail-closed) closure. |
| `artifacts/env/python312.json` | Full captured environment descriptor. |
| `envs/python312.lock` | Pin-only lock of the direct required dependencies. |

Regenerate the descriptor:

```bash
python scripts/ci/check_env_preflight.py --emit-descriptor artifacts/env/python312.json
```

Run the gate (exit 0 = pass, exit 1 = fail-closed):

```bash
python scripts/ci/check_env_preflight.py          # descriptor-gate (this env)
python scripts/ci/check_env_preflight.py --strict # hermetic gate (ENV-005 image)
```

## The hard contract (fail-closed)

The gate exits non-zero if **any** of these is violated:

1. The interpreter is not **Python 3.12.x**.
2. **pandas** is missing or below the named floor **`>= 2.3.3`**.
3. Any **required dependency** from `requirements.txt` is not installed / not
   resolvable via `importlib.metadata`.

The gate resolves installed versions directly from real distribution metadata
and reads floors straight from `requirements.txt`. **It does not rely on any
"audit shim"** — no stub module, no `sitecustomize` monkeypatch, and no
compatibility placeholder is consulted to decide whether the environment is
healthy. (`sitecustomize.py` still applies its own security hardening at
interpreter start; the preflight simply does not depend on it for its verdict.)

## Below-floor deviations (this sandbox is pre-hermetic)

On the current execution sandbox all **46** required dependencies are present
and importable, Python is 3.12.3, and pandas is exactly 2.3.3 — the hard
contract **PASSES**. However, **8** dependencies are installed at versions
**below** their `requirements.txt` floors:

| Dependency | Installed | Required floor |
| --- | --- | --- |
| networkx | 2.6.3 | `>= 3.5` |
| fastapi | 0.135.2 | `>= 0.139.0, < 1.0.0` |
| PyJWT | 2.12.1 | `>= 2.13.0` |
| cryptography | 46.0.6 | `>= 49.0.0` |
| aiohttp | 3.13.3 | `>= 3.14.1` |
| starlette | 1.0.0 | `>= 1.3.1` |
| tornado | 6.5.5 | `>= 6.5.7` |
| python-multipart | 0.0.22 | `>= 0.0.32` |

Most of these are the **security-hardened floors** mirrored from
`constraints/security.txt`. This sandbox is **not** a hermetic container, so it
has not been rebuilt against those floors. Per the ENV-001 severity model these
are reported as **non-fatal deviations** and do **not** fail the descriptor gate;
`--strict` promotes every one of them to a hard failure so the **same** gate can
certify an ENV-005 hermetic image once it is built. Raising these floors is
**ENV-005's** responsibility, not ENV-001's.

## Lock file: pin-only, hashes are an ENV-005 follow-up

`envs/python312.lock` is a **pin-only** lock: it records the exact `==` versions
of the direct required dependencies actually resolved on this interpreter.

**It carries no `--hash` values.** Full hash-locking
(`pip-compile --generate-hashes` / `pip hash`) must be produced against a
hermetic, pinned index as part of ENV-005; doing it here would re-resolve to the
canonical floors and produce versions that do **not** match this sandbox,
breaking the descriptor's internal consistency. **No sha256 hashes were
fabricated.** The below-floor pins are annotated `# BELOW-FLOOR` in the lock.

The full transitive, hash-less resolution already lives in `requirements.lock`
(a read-only reference here; ENV-001 does not regenerate it).

## Closure evidence

```bash
python -m pytest tests/ci/test_env_preflight.py -q   # positive + negative, fail-closed
python scripts/ci/check_env_preflight.py             # exit 0 on this env
python -m pytest tests/unit/utils --collect-only -q  # collection starts, no env-blocker
python -m ruff check                                 # clean
```
