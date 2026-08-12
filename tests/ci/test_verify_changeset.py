from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "verify_changeset.py"
spec = importlib.util.spec_from_file_location("verify_changeset", MODULE_PATH)
assert spec is not None and spec.loader is not None
vc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = vc
spec.loader.exec_module(vc)


def test_tail_keeps_last_nonempty_lines() -> None:
    text = "a\n\nb\n\n\nc\nd"
    assert vc._tail(text, lines=2) == "c\nd"


def test_bandit_prefix_selection_matches_ci_contract() -> None:
    # CI scans only these first-party trees with bandit.
    assert "core/indicators/cache.py".startswith(vc._BANDIT_PREFIXES)
    assert "src/admin/remote_control.py".startswith(vc._BANDIT_PREFIXES)
    assert "application/api/service.py".startswith(vc._BANDIT_PREFIXES) is False
    assert "tests/ci/test_x.py".startswith(vc._BANDIT_PREFIXES) is False


def test_fail_closed_on_unverified(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # A missing tool (UNVERIFIED) must fail the run — never report success for
    # something that was not actually checked.
    monkeypatch.setattr(
        vc,
        "verify",
        lambda base_ref: [
            vc.GateResult("ruff", vc.PASS),
            vc.GateResult("mypy", vc.UNVERIFIED, "tool 'mypy' not installed"),
        ],
    )
    assert vc.main(["--base-ref", "origin/main"]) == 1


def test_fail_on_gate_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        vc,
        "verify",
        lambda base_ref: [
            vc.GateResult("ruff", vc.PASS),
            vc.GateResult("black", vc.FAIL, "would reformat x.py"),
        ],
    )
    assert vc.main([]) == 1


def test_ok_when_all_pass_or_skip(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        vc,
        "verify",
        lambda base_ref: [
            vc.GateResult("ruff", vc.PASS),
            vc.GateResult("black", vc.SKIP, "not applicable"),
            vc.GateResult("commit-acceptor", vc.PASS),
        ],
    )
    out = tmp_path / "report.json"
    assert vc.main(["--json", str(out)]) == 0
    assert out.is_file()
    assert '"ok": true' in out.read_text(encoding="utf-8")


def test_actionlint_gate_skips_without_workflow_change() -> None:
    assert vc._actionlint_gate(workflows_changed=False).status == vc.SKIP


def test_actionlint_gate_unverified_when_binary_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(vc.shutil, "which", lambda _name: None)
    r = vc._actionlint_gate(workflows_changed=True)
    assert r.status == vc.UNVERIFIED
