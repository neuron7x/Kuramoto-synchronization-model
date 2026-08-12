# COMMAND_LOG

| # | Command | Result | Classification |
|---|---|---|---|
| 1 | `git worktree add --detach /home/neuro7/gs-cov-audit origin/main` | a59e5c7e | clean baseline |
| 2 | `python -c "import core"` (worktree cwd) | resolves to worktree, not rogue `/home/neuro7/GeoSync` | rogue-install neutralised |
| 3 | `pytest --collect-only -q` | 18 185 tests / 1 463 files / 0 errors | inventory |
| 4 | `coverage run --branch --source=core/kuramoto -m pytest <55 kuramoto-importing files> -m "not slow"` | pkg 84.06%; engine.py 91.19% | baseline (scoped) |
| 5 | prototype Richardson RK4 order | ratio 16.28, log2 4.02 | confirms p=4 oracle |
| 6 | `pytest test_kuramoto_engine_numerical_hardening.py` | 11 passed | new tests green |
| 7 | mutant: RK4→Euler | convergence test **FAILED** | mutant killed |
| 8 | mutant: drop order_parameter finiteness guard | non-finite test **FAILED** | mutant killed |
| 9 | mutant: drop `_dtheta_dt` finiteness guard | overflow test **FAILED** | mutant killed |
| 10 | restore engine.py | `diff` identical | no runtime change shipped |
| 11 | `coverage ... engine + hardening` | engine.py **91.19% → 94.97%** (83,85,271 closed) | gap closed |
| 12 | `ruff check` / `ruff format --check` / `black --check` (off-exclude copy) | clean after autofix | lint green |
| 13 | `mypy --strict <new file>` | Success: no issues | type-clean |
| 14 | `pytest test_T28...ott_antonsen_unit_disk_bound_property` | FAILED (R0≈1e-197) | **pre-existing**, out of scope, recorded |

Gates NOT run (recorded, not hidden): full 18k single-process suite (not the
oracle — CI fast-shards are); `mutmut` (not configured — manual mutation done);
`bandit`/`pip-audit`/`detect-secrets` (no runtime/dependency change in this
tests-only PR). `tests/` is config-excluded from ruff/black/mypy in CI
(`pyproject.toml` force-exclude), so python-quality passes by exclusion;
cleanliness verified manually anyway.
