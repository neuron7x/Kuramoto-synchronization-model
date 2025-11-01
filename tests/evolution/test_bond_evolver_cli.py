from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_bond_evolver_cli_generates_output(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    output_path = tmp_path / "optimized.json"

    result = subprocess.run(
        [
            sys.executable,
            "evolution/bond_evolver.py",
            "--generations",
            "1",
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert output_path.exists(), result.stdout

    payload = json.loads(output_path.read_text())
    assert "nodes" in payload and isinstance(payload["nodes"], list)
    assert "edges" in payload and isinstance(payload["edges"], list)
    assert any(edge.get("type") for edge in payload["edges"])
    assert "[bond_evolver] saved" in result.stdout
