from pathlib import Path

from scripts.check_config_single_source import check_config_single_source
from scripts.check_namespace_integrity import check_namespace_integrity
from scripts.check_single_entrypoint import check_single_entrypoint


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_namespace_integrity_has_no_violations() -> None:
    assert check_namespace_integrity(REPO_ROOT) == []


def test_single_entrypoint_guard_has_no_violations() -> None:
    assert check_single_entrypoint(REPO_ROOT) == []


def test_config_single_source_guard_has_no_violations() -> None:
    assert check_config_single_source(REPO_ROOT) == []
