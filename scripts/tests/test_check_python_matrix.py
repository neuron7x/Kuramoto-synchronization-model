from pathlib import Path

import pytest

import scripts.check_python_matrix as mod


def test_parse_requires_python(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.10,<3.13"\n')

    assert mod.parse_requires_python(pyproject) == ("3.10", "3.13")


def test_check_workflows_detects_out_of_range(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow_file = workflow_dir / "ci.yml"
    workflow_file.write_text(
        "jobs:\n  build:\n    strategy:\n      matrix:\n"
        "        python-version: ['3.9', '3.10']\n"
    )

    issues = mod.check_workflows(tmp_path, "3.10", "3.13")

    assert any("3.9" in issue for issue in issues)


def test_main_exits_non_zero_on_mismatch(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    pyproject = repo_root / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.11,<3.13"\n')

    workflow_dir = repo_root / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("python-version: ['3.11', '3.13']\n")

    module_root = Path(mod.__file__).parent.parent
    real_resolve = mod.Path.resolve

    def fake_resolve(self):
        if self == module_root:
            return repo_root
        return real_resolve(self)

    monkeypatch.setattr(mod.Path, "resolve", fake_resolve)

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 1
