from __future__ import annotations

from pathlib import Path

from tools.ci.check_actions_pinned import find_unpinned_actions


FIXTURES = Path(__file__).parent / "fixtures" / "workflows"


def test_skips_pinned_and_local_actions() -> None:
    findings = find_unpinned_actions([FIXTURES / "pinned.yml"])

    assert findings == []


def test_flags_unpinned_actions() -> None:
    findings = find_unpinned_actions([FIXTURES / "unpinned.yml"])

    assert len(findings) == 2
    assert all("actions/" in ref for _, ref in findings)


def test_raises_on_invalid_yaml(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yml"
    broken.write_text("uses: actions/checkout@v5: !!not-valid")

    findings = find_unpinned_actions([broken])

    assert findings and "actions/checkout@v5" in findings[0][1]
