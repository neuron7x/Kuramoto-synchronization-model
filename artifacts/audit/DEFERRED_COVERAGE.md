# DEFERRED_COVERAGE — next smallest PR scopes

Honest scope statement: this PR is the **first, focused increment** of the full
audit charter — the CRITICAL RK4 integrator (`core/kuramoto/engine.py`). The
items below are deferred with exact next actions, per the charter's "next
smallest PR scope" rule and the "do not mix large rewrite with coverage PR" /
"no import-only coverage games" constraints.

| File | Symbol | Reason deferred | Next action |
|---|---|---|---|
| engine.py | L166 `run` non-finite phase | defence-in-depth; `_dtheta_dt` guard fires first | leave covered-by-design; document only |
| engine.py | L237/241/248 `_validate_runtime_inputs` | unreachable via public `KuramotoConfig` (validates shape/finiteness upstream) | leave; would require monkeypatch (forbidden) |
| metrics.py | L89/91/93/95 `MetricsConfig.__post_init__` | config validation branches, cheap | small fail-closed param-test PR |
| metrics.py | L416-425 `_edge_entropy` | private; needs 3-D `K_series` fixture | metamorphic test (static K → 0.0; permuted edges) |
| falsification.py | 135-160, 269-343 (counterfactuals) | **HIGH residual is `-m slow` deselection** — verify the T25 surrogate suite covers these in a full (non-fast) run BEFORE claiming a gap | run `pytest tests/unit/physics/test_T25_falsification_surrogates.py` (no slow filter) + measure; only then test true residual |
| kuramoto_ricci_engine.py | 139/142/182/271-275 | HIGH, separate INV-KR domain | dedicated INV-KR1..3 boundary PR |
| ricci_flow_engine.py | 26 lines | HIGH, separate Ricci domain | dedicated PR |
| jax_engine.py | 53-243 (27.5%) | optional backend; `jax` not installed in this env | gate behind `pytest.importorskip("jax")`; CI optional-deps job |
| (charter) claim-governance, release-evidence, schema, security | not started | out of this PR's module scope | separate PRs per `scripts/ci/check_claims.py`, `tools/release_evidence_harness.py`, `schemas/research/*.schema.json` |

## Pre-existing failure (not introduced here, not fixed here)

`test_T28_wave2_witnesses.py::test_ott_antonsen_unit_disk_bound_property` —
Hypothesis edge at `R0→0` (unstable OA fixed point). Next action: bound the
`R0` strategy away from 0 in `ott_antonsen.py`'s test, OR add an explicit
incoherent-fixed-point branch — a separate `ott_antonsen` PR.
