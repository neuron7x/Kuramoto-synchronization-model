from __future__ import annotations

from pathlib import Path

import yaml

from tools.codegen import CodegenEngine, load_config


def _write_config(tmp_path: Path, output_path: Path) -> Path:
    config = {
        "runtime": {
            "cache_dir": str(tmp_path / "cache"),
            "artifacts_dir": str(tmp_path / "artifacts"),
            "version_file": "VERSION",
        },
        "tasks": [
            {
                "name": "simple-dto",
                "generator": "dto",
                "sources": ["tests/tools/data/schemas/simple.json"],
                "template": "tests/tools/data/templates/simple_dto.py.j2",
                "output": str(output_path),
                "publish_artifact": False,
                "metadata": {"default_model_name": "SimpleDto"},
            }
        ],
    }
    config_path = tmp_path / "codegen.yaml"
    yaml.safe_dump(config, config_path.open("w", encoding="utf-8"))
    return config_path


def test_engine_is_idempotent(tmp_path: Path) -> None:
    output_path = tmp_path / "generated.py"
    config_path = _write_config(tmp_path, output_path)
    engine = CodegenEngine(load_config(config_path))

    first = engine.run()
    second = engine.run()

    assert first[0].updated is True
    assert second[0].updated is False
    fingerprint_path = tmp_path / "cache" / "simple-dto.sha256"
    assert fingerprint_path.exists()
    fingerprint = fingerprint_path.read_text(encoding="utf-8")

    output_path.write_text("# mutated", encoding="utf-8")
    try:
        engine.run(check=True)
    except RuntimeError:
        pass
    else:  # pragma: no cover - defensive check
        raise AssertionError("Expected RuntimeError when running in check mode with changes")
    assert fingerprint_path.read_text(encoding="utf-8") == fingerprint
