# SPDX-License-Identifier: MIT
"""C4 — adversarial self-audit of the privileged phase-offset estimator.

C3's conclusion ("the channel is recoverable in principle, so the standard
estimands' blindness is their property, not a ground-truth defect") rested
on a *privileged* mean-gamma-phase-offset estimator. By our own fail-closed
discipline that escape-hatch must itself survive a positive control, a
confound-rejection gate, a sign-flip negative control, and a parameter
sweep — otherwise "recoverable in principle" is a self-lie. C4 turns the
instrument on our own conclusion. ``run`` lives in
``research.ctc_falsify.c4.run``.
"""

__all__: list[str] = []
