# BASELINE — lab-pilot/kuramoto-ricci-contracts
captured_on_commit: 53f21b3b

## python -V
Python 3.12.3

## compileall core (kuramoto only)
compileall: OK
## tool versions
ruff 0.14.0
black, 26.3.1 (compiled: yes)
Python (CPython) 3.12.3
mypy 1.18.2 (compiled: yes)

## baseline pytest (existing kuramoto contracts)
..........................                                               [100%]

## baseline ruff core/kuramoto
All checks passed!
## baseline black --check core/kuramoto
All done! ✨ 🍰 ✨
34 files would be left unchanged.

## POST-STATE (after Stream-1 slice)
- ruff: PASS  | black: PASS  | mypy --strict: PASS (35 files)
- new tests: 20 PASS  | kuramoto unit regression: 332 PASS / 1 pre-existing skip
- new noqa/type:ignore introduced: 0 (debt ratchet delta = 0)
