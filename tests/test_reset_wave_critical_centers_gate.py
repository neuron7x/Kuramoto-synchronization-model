"""CI gate: every reset-wave critical center must PASS.

`audit_critical_centers()` enumerates the seven integration-readiness
centers declared in `docs/reset_wave_critical_centers.md`:

  1. phase_manifold_wrapping
  2. numerical_stability_region
  3. fail_closed_lock
  4. deterministic_replay
  5. nonconvergence_detection
  6. regime_interpretation_layer
  7. contract_validation

Pre-cycle-#4 the audit was callable only ad-hoc. This test wires it
into pytest, so any future commit that breaks any of the seven centers
fails CI immediately rather than waiting for a manual probe.
"""

from __future__ import annotations

from geosync.neuroeconomics.reset_wave_engine import (
    audit_critical_centers,
)

EXPECTED_CENTERS = (
    "phase_manifold_wrapping",
    "numerical_stability_region",
    "fail_closed_lock",
    "deterministic_replay",
    "nonconvergence_detection",
    "regime_interpretation_layer",
    "contract_validation",
)


def test_audit_returns_seven_named_centers_in_canonical_order() -> None:
    audits = audit_critical_centers()
    assert len(audits) == 7
    assert tuple(a.center for a in audits) == EXPECTED_CENTERS


def test_every_critical_center_passes() -> None:
    audits = audit_critical_centers()
    failed = [a for a in audits if not a.passed]
    assert not failed, "critical centers failing: " + ", ".join(
        f"{a.center} ({a.detail})" for a in failed
    )


def test_each_center_has_non_empty_detail_string() -> None:
    """No silent center: every audit row must explain what it covers."""
    audits = audit_critical_centers()
    for a in audits:
        assert isinstance(a.detail, str) and a.detail.strip(), (
            f"{a.center} has empty detail — gate would not be auditable"
        )
