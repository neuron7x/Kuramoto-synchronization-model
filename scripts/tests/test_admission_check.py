from __future__ import annotations

import scripts.admission_check as admission


def test_main_passes_when_checks_succeed(monkeypatch) -> None:
    monkeypatch.setattr(admission, "_validate_monotonic_acceptance", lambda: True)
    monkeypatch.setattr(admission, "_validate_monotonic_rejection", lambda: True)

    assert admission.main() == 0


def test_main_fails_when_check_rejects(monkeypatch) -> None:
    monkeypatch.setattr(admission, "_validate_monotonic_acceptance", lambda: True)
    monkeypatch.setattr(admission, "_validate_monotonic_rejection", lambda: False)

    assert admission.main() == 1
