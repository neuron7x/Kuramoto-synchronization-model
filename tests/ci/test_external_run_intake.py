# SPDX-License-Identifier: MIT
"""Contracts for fail-closed external run repair intake."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ci" / "external_run_intake.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("external_run_intake", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_pyproject(root: Path, name: str) -> None:
    (root / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n', encoding="utf-8")


def _clean_git(monkeypatch, m: ModuleType, branch: str = "work") -> None:
    monkeypatch.setattr(m, "_read_branch", lambda root: branch)
    monkeypatch.setattr(m, "_read_git_sha", lambda root: "abc123")
    monkeypatch.setattr(m, "_read_git_dirty", lambda root: False)


def test_mismatched_workspace_fails_closed(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "geosync")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(m, "_read_remotes", lambda root: [])

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive")

    assert result.status == "FAIL"
    assert result.repair_allowed is False
    assert "REPOSITORY_IDENTITY_MISMATCH" in result.blockers
    assert "MISSING_GIT_REMOTE" in result.blockers


def test_matching_workspace_with_target_remote_allows_repair(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    _clean_git(monkeypatch, m, branch="fix/release-gate")
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [
            m.RemoteEntry("origin", "https://github.com/neuron7xLab/bive.git", "fetch", "neuron7xlab/bive", "github.com")
        ],
    )

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive")

    assert result.status == "PASS"
    assert result.repair_allowed is True
    assert result.target_repo_slug == "neuron7xlab/bive"
    assert result.blockers == []


def test_remote_for_wrong_repository_is_blocker(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [
            m.RemoteEntry(
                "origin",
                "https://github.com/neuron7xLab/geosync.git",
                "fetch",
                "neuron7xlab/geosync",
                "github.com",
            )
        ],
    )

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive")

    assert result.status == "FAIL"
    assert result.repair_allowed is False
    assert result.blockers == ["TARGET_REMOTE_NOT_CONFIGURED"]


def test_remote_same_slug_on_untrusted_host_does_not_match(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [
            m.RemoteEntry(
                "origin",
                "https://evil.example/neuron7xLab/bive.git",
                "fetch",
                "neuron7xlab/bive",
                "evil.example",
            )
        ],
    )

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive")

    assert result.status == "FAIL"
    assert result.blockers == ["TARGET_REMOTE_NOT_CONFIGURED"]


def test_remote_substring_spoof_does_not_match(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [
            m.RemoteEntry("origin", "https://github.com/attacker/not-bive.git", "fetch", "attacker/not-bive", "github.com")
        ],
    )

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive")

    assert result.status == "FAIL"
    assert result.blockers == ["TARGET_REMOTE_NOT_CONFIGURED"]



def test_github_actions_run_url_normalizes_to_repository_slug() -> None:
    m = _load()

    slug = m._repo_slug("https://github.com/neuron7xLab/bive/actions/runs/27351344416")

    assert slug == "neuron7xlab/bive"

def test_dirty_worktree_blocks_by_default(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    monkeypatch.setattr(m, "_read_branch", lambda root: "work")
    monkeypatch.setattr(m, "_read_git_sha", lambda root: "abc123")
    monkeypatch.setattr(m, "_read_git_dirty", lambda root: True)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [m.RemoteEntry("origin", "git@github.com:neuron7xLab/bive.git", "fetch", "neuron7xlab/bive", "github.com")],
    )

    result = m.assess_workspace(tmp_path, "https://github.com/neuron7xLab/bive.git")

    assert result.status == "FAIL"
    assert result.git_dirty is True
    assert result.blockers == ["DIRTY_WORKTREE"]


def test_dirty_worktree_can_be_reported_without_blocking(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    monkeypatch.setattr(m, "_read_branch", lambda root: "work")
    monkeypatch.setattr(m, "_read_git_sha", lambda root: "abc123")
    monkeypatch.setattr(m, "_read_git_dirty", lambda root: True)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [m.RemoteEntry("origin", "git@github.com:neuron7xLab/bive.git", "fetch", "neuron7xlab/bive", "github.com")],
    )

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive", allow_dirty=True)

    assert result.status == "PASS"
    assert result.git_dirty is True
    assert result.repair_allowed is True


def test_malformed_pyproject_fails_closed(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [m.RemoteEntry("origin", "https://github.com/neuron7xLab/bive.git", "fetch", "neuron7xlab/bive", "github.com")],
    )

    result = m.assess_workspace(tmp_path, "neuron7xLab/bive")

    assert result.status == "FAIL"
    assert result.blockers == ["UNREADABLE_PYPROJECT"]


def test_untrusted_target_host_fails_closed(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(
        m,
        "_read_remotes",
        lambda root: [
            m.RemoteEntry(
                "origin",
                "https://github.com/neuron7xLab/bive.git",
                "fetch",
                "neuron7xlab/bive",
                "github.com",
            )
        ],
    )

    result = m.assess_workspace(tmp_path, "https://evil.example/neuron7xLab/bive")

    assert result.status == "FAIL"
    assert "UNTRUSTED_TARGET_HOST" in result.blockers


def test_invalid_target_repo_fails_closed(monkeypatch, tmp_path: Path) -> None:
    m = _load()
    _write_pyproject(tmp_path, "bive")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(m, "_read_remotes", lambda root: [])

    result = m.assess_workspace(tmp_path, "bive")

    assert result.status == "FAIL"
    assert "INVALID_TARGET_REPO" in result.blockers
    assert "INVALID_EXPECTED_PACKAGE" in result.blockers


def test_cli_outputs_machine_readable_failure(monkeypatch, tmp_path: Path, capsys) -> None:
    m = _load()
    _write_pyproject(tmp_path, "geosync")
    _clean_git(monkeypatch, m)
    monkeypatch.setattr(m, "_read_remotes", lambda root: [])

    rc = m.main(["--root", str(tmp_path), "--target-repo", "neuron7xLab/bive"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert payload["status"] == "FAIL"
    assert payload["repair_allowed"] is False
    assert payload["first_file_to_open"] == "pyproject.toml"
    assert payload["git_sha"] == "abc123"
