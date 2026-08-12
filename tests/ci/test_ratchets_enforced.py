# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Make the code-hygiene / import-architecture ratchets ENFORCING.

The ratchet checkers run in their own gate workflows (code-hygiene-gate,
import-architecture-gate) — but those are NOT branch-protection required, so
their verdict could not block a merge. This test runs the three git-light
ratchets inside the REQUIRED python-fast-tests suite, so a PR that adds a god
function, broad except, ambient nondeterminism, runtime print, test skip,
src.* import or sys.path hack WITHOUT paying it into the baseline now fails a
required check.

Scope: the meta-gate (check_debt_baseline_monotonic, anti-laundering) needs the
origin/main baseline and is enforced by the code-hygiene-gate workflow being a
required check — not here, to avoid a network/shallow-checkout dependency.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CHECKERS = [
    "scripts/ci/check_code_hygiene.py",
    "scripts/ci/check_skip_ratchet.py",
    "scripts/ci/check_import_architecture.py",
]


@pytest.mark.parametrize("checker", _CHECKERS)
def test_ratchet_holds_on_current_tree(checker: str) -> None:
    proc = subprocess.run(
        [sys.executable, checker],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"{checker} FAILED (a required ratchet rejected the current tree). "
        f"New debt must be refactored away or paid into its baseline with "
        f"`python {checker} --write` (only when paying DOWN).\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
