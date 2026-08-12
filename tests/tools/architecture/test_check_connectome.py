from __future__ import annotations

from pathlib import Path

import pytest

from tools.architecture.check_connectome import main, validate_repository


def write_contract(path: Path, root: Path) -> None:
    contract = f"""
version: "test"
system_name: "GeoSync-NPQ-OS-Test"
scan_roots:
  - "{(root / 'geosync').as_posix()}"
domains:
  sensory:
    state: "active"
    owner: "data@geosync"
    paths:
      - "{(root / 'geosync/cortex/sensory').as_posix()}"
    import_roots:
      - "geosync/cortex/sensory"
    role: "data ingestion"
    allowed_imports: []
    forbidden_imports:
      - "geosync/cortex/motor"
  hippocampus:
    state: "active"
    owner: "memory@geosync"
    paths:
      - "{(root / 'geosync/cortex/hippocampus').as_posix()}"
    import_roots:
      - "geosync/cortex/hippocampus"
    role: "memory"
    allowed_imports:
      - "geosync/cortex/sensory"
    forbidden_imports:
      - "geosync/cortex/motor"
  motor:
    state: "reserved"
    owner: "execution@geosync"
    paths:
      - "{(root / 'geosync/cortex/motor').as_posix()}"
    import_roots:
      - "geosync/cortex/motor"
    role: "execution"
    allowed_imports: []
    forbidden_imports:
      - "geosync/research"
      - "geosync/physics"
"""
    path.write_text(contract, encoding="utf-8")


def test_forbidden_import_is_reported(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text("from geosync.cortex.motor import venue\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].domain == "sensory"
    assert violations[0].imported == "geosync.cortex.motor"
    assert "strictly forbidden" in violations[0].reason


def test_import_from_child_alias_is_governed(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text("from geosync.cortex import motor\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].domain == "sensory"
    assert violations[0].imported == "geosync.cortex.motor"
    assert "strictly forbidden" in violations[0].reason


def test_allowed_cross_domain_import_passes(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/hippocampus/memory.py"
    module.parent.mkdir(parents=True)
    module.write_text("import geosync.cortex.sensory.contracts\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert violations == []


def test_unlisted_cross_domain_import_is_reported(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/motor/execution.py"
    module.parent.mkdir(parents=True)
    module.write_text("import geosync.cortex.hippocampus.memory\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert "absent from allowed_imports" in violations[0].reason


def test_external_imports_are_not_governed(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text("import pathlib\nimport numpy as np\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert violations == []


def test_relative_import_resolves_to_governed_prefix(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text("from ..motor import venue\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].imported == "geosync.cortex.motor"


def test_literal_dynamic_import_is_governed(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import importlib\nimportlib.import_module('geosync.cortex.motor.venue')\n",
        encoding="utf-8",
    )

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].statement == "dynamic import geosync.cortex.motor.venue"


def test_importlib_alias_dynamic_import_is_governed(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import importlib as il\nil.import_module('geosync.cortex.motor.venue')\n",
        encoding="utf-8",
    )

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].statement == "dynamic import geosync.cortex.motor.venue"


def test_import_module_callable_alias_dynamic_import_is_governed(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        (
            "from importlib import import_module as load_module\n"
            "load_module('geosync.cortex.motor.venue')\n"
        ),
        encoding="utf-8",
    )

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].statement == "dynamic import geosync.cortex.motor.venue"


def test_contract_without_owner_fails_closed(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    contract_path.write_text(
        """
version: "test"
system_name: "GeoSync-NPQ-OS-Test"
domains:
  sensory:
    path: "geosync/cortex/sensory"
    role: "data ingestion"
    allowed_imports: []
    forbidden_imports: []
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="missing institutional owner"):
        validate_repository(contract_path=contract_path)


def test_json_cli_reports_machine_readable_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text("from geosync.cortex.motor import venue\n", encoding="utf-8")

    exit_code = main(["--contract", contract_path.as_posix(), "--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"domain": "sensory"' in captured.out
    assert '"imported": "geosync.cortex.motor"' in captured.out
