from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "test-pr-locally.sh"


def test_shell_gate_is_only_a_compatibility_wrapper():
    content = WRAPPER.read_text(encoding="utf-8")

    assert "tools/ci/pr_preflight.py" in content
    assert "FIRST_FILE_TO_OPEN=" in content
    for forbidden in (
        "|| true",
        "--exit-zero",
        "2>/dev/null",
        "ruff check",
        "black --check",
        "mypy --no-error-summary",
        "pytest tests/",
        "detect-secrets scan",
    ):
        assert forbidden not in content
