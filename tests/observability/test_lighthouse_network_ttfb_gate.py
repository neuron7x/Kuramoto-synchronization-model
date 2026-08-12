# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""IERD-Q6 network_TTFB Lighthouse-CI budget gate (Phase-4 EXIT, #531).

This is the cited regression target for the ``network_TTFB`` layer in
``tests/observability/test_latency_layer_coverage.py``. It statically
falsifies the contract that the Lighthouse-CI gate genuinely closes the
final §5 latency layer:

* the workflow ``.github/workflows/lighthouse-ci.yml`` builds the REAL
  Next app, serves it, runs ``lhci autorun``, and is **not**
  ``continue-on-error`` (so an ``error``-level budget violation fails
  the build);
* the budget config ``apps/web/lighthouserc.json`` pins the §5 TTFB
  budget (``server-response-time`` < 300 ms) and the client_render FCP
  budget (``first-contentful-paint`` < 1.0 s) at ``error`` level;
* the workflow carries a falsifier that tightens TTFB to 1 ms and
  asserts the run FAILS — proving the budget is enforced, not
  decorative.

These are static-structure assertions (no browser): the actual
real-network measurement runs in CI via the Lighthouse workflow itself.
The dynamic green/falsifier proof lives in that workflow; this module is
the unit-CI guard that the gate cannot silently regress (e.g. someone
flipping the assertion from ``error`` to ``warn`` or adding
``continue-on-error``).

Tracks claim ``e2e-latency-budget-compliance`` and issue IERD-Q6
(#531).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_WORKFLOW: Final[Path] = _REPO_ROOT / ".github" / "workflows" / "lighthouse-ci.yml"
_CONFIG: Final[Path] = _REPO_ROOT / "apps" / "web" / "lighthouserc.json"

# §5 budgets, in milliseconds.
_TTFB_BUDGET_MS: Final[int] = 300
_FCP_BUDGET_MS: Final[int] = 1000


def _config() -> dict[str, Any]:
    spec: dict[str, Any] = json.loads(_CONFIG.read_text(encoding="utf-8"))
    return spec


def test_lighthouse_config_exists_and_serves_real_app() -> None:
    """The budget config drives a real served Next build, not a stub."""
    assert _CONFIG.is_file(), f"missing Lighthouse budget config at {_CONFIG}"
    collect = _config()["ci"]["collect"]
    assert "next start" in collect["startServerCommand"] or "npm run start" in (
        collect["startServerCommand"]
    ), "Lighthouse must measure a genuinely served Next build (startServerCommand)."
    urls = collect["url"]
    assert any("/signin" in u for u in urls), (
        "Lighthouse must hit the public /signin route (static prerender, no "
        "auth redirect) so TTFB/FCP are measured against a real server."
    )
    assert int(collect["numberOfRuns"]) >= 1, "must run Lighthouse at least once"


def test_lighthouse_ttfb_budget_fail_closed() -> None:
    """network_TTFB: server-response-time < 300 ms is an error-level gate.

    This is THE assertion the layer-coverage matrix cites. If the TTFB
    budget is missing, downgraded to ``warn``, or detuned off §5, this
    fails — the layer is not genuinely gated.
    """
    assertions = _config()["ci"]["assert"]["assertions"]
    assert "server-response-time" in assertions, (
        "network_TTFB budget (server-response-time) absent from "
        "lighthouserc.json — the layer is not gated."
    )
    level, opts = assertions["server-response-time"]
    assert level == "error", (
        f"network_TTFB budget must be error-level (fail-closed); got {level!r}. "
        "A warn-level budget cannot fail the build."
    )
    assert opts["maxNumericValue"] == _TTFB_BUDGET_MS, (
        f"network_TTFB budget must be the §5 {_TTFB_BUDGET_MS} ms; "
        f"got {opts['maxNumericValue']}."
    )


def test_lighthouse_fcp_budget_fail_closed() -> None:
    """client_render: first-contentful-paint < 1.0 s is an error-level gate."""
    assertions = _config()["ci"]["assert"]["assertions"]
    level, opts = assertions["first-contentful-paint"]
    assert level == "error", f"FCP budget must be error-level; got {level!r}."
    assert opts["maxNumericValue"] == _FCP_BUDGET_MS, (
        f"FCP budget must be the §5 {_FCP_BUDGET_MS} ms; got {opts['maxNumericValue']}."
    )


def test_lighthouse_workflow_is_fail_closed() -> None:
    """The Lighthouse workflow must run lhci and NOT be continue-on-error."""
    assert _WORKFLOW.is_file(), f"missing Lighthouse CI workflow at {_WORKFLOW}"
    src = _WORKFLOW.read_text(encoding="utf-8")
    assert "lhci autorun" in src, "workflow must invoke `lhci autorun`."
    assert "npm run build" in src, "workflow must build the real Next app before measuring."
    assert "continue-on-error" not in src, (
        "the Lighthouse gate must be fail-closed; `continue-on-error` would "
        "make the §5 budget decorative."
    )


def test_lighthouse_workflow_carries_budget_falsifier() -> None:
    """A 1 ms-TTFB falsifier step must prove the budget is non-decorative."""
    src = _WORKFLOW.read_text(encoding="utf-8")
    assert "Falsifier" in src, "workflow must carry an explicit falsifier step."
    assert re.search(r"1\s*ms", src), "falsifier must tighten the TTFB budget to 1 ms."
    assert "maxNumericValue: 1" in src, (
        "falsifier must set the TTFB budget to 1 ms (impossible for a real "
        "server) and assert the run FAILS."
    )
