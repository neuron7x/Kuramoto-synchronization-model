from __future__ import annotations

import importlib
import sys
import types


def _load_module(monkeypatch):
    dummy = types.ModuleType("runtime.thermo_controller")
    dummy.MetricsSnapshot = type("MetricsSnapshot", (), {})
    dummy.ThermoController = type("ThermoController", (), {})
    monkeypatch.setitem(sys.modules, "runtime.thermo_controller", dummy)
    return importlib.reload(importlib.import_module("scripts.admission_check"))


def test_main_passes_when_checks_succeed(monkeypatch) -> None:
    admission = _load_module(monkeypatch)
    monkeypatch.setattr(admission, "_validate_monotonic_acceptance", lambda: True)
    monkeypatch.setattr(admission, "_validate_monotonic_rejection", lambda: True)

    assert admission.main() == 0


def test_main_fails_when_check_rejects(monkeypatch) -> None:
    admission = _load_module(monkeypatch)
    monkeypatch.setattr(admission, "_validate_monotonic_acceptance", lambda: True)
    monkeypatch.setattr(admission, "_validate_monotonic_rejection", lambda: False)

    assert admission.main() == 1
