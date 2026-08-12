from __future__ import annotations

from pathlib import Path

from tools.architecture.check_connectome import validate_repository


def write_contract(path: Path, root: Path) -> None:
    contract = f"""
version: "test"
system_name: "GeoSync-NPQ-OS-Edge-Test"
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
  motor:
    state: "reserved"
    owner: "execution@geosync"
    paths:
      - "{(root / 'geosync/cortex/motor').as_posix()}"
    import_roots:
      - "geosync/cortex/motor"
    role: "execution"
    allowed_imports: []
    forbidden_imports: []
"""
    path.write_text(contract, encoding="utf-8")


def test_forbidden_import_dominates_broad_allowed_import(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    text = contract_path.read_text(encoding="utf-8")
    text = text.replace(
        "    allowed_imports: []\n    forbidden_imports:",
        '    allowed_imports:\n      - "geosync/cortex"\n    forbidden_imports:',
        1,
    )
    contract_path.write_text(text, encoding="utf-8")
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text("import geosync.cortex.motor.venue\n", encoding="utf-8")

    violations = validate_repository(contract_path=contract_path)

    assert len(violations) == 1
    assert violations[0].imported == "geosync.cortex.motor.venue"
    assert "strictly forbidden" in violations[0].reason


def test_non_literal_dynamic_import_is_declared_static_boundary(tmp_path: Path) -> None:
    contract_path = tmp_path / "connectome.yaml"
    write_contract(contract_path, tmp_path)
    module = tmp_path / "geosync/cortex/sensory/feed.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import importlib\nname = 'geosync.cortex.motor.venue'\nimportlib.import_module(name)\n",
        encoding="utf-8",
    )

    violations = validate_repository(contract_path=contract_path)

    assert violations == []
