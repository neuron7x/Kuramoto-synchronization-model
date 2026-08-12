# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
from pathlib import Path

from scripts import resilient_data_sync
from scripts.runtime import EXIT_CODES, compute_checksum


def test_resilient_data_sync_smoke(tmp_path, capsys) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sample = repo_root / "sample.csv"
    assert sample.exists(), "expected bundled sample.csv to exist"

    dest_root = tmp_path / "artifacts"
    checksum = compute_checksum(sample)

    exit_code = resilient_data_sync.main(
        [
            str(sample),
            "--artifact-root",
            str(dest_root),
            "--checksum",
            f"{sample}={checksum}",
            "--json",
        ]
    )

    assert exit_code == EXIT_CODES["success"]

    stdout = capsys.readouterr().out
    json_offset = stdout.index("[")
    summary = json.loads(stdout[json_offset:])

    assert len(summary) == 1
    entry = summary[0]
    destination = Path(entry["destination"])
    assert destination.exists()
    assert destination.read_bytes() == sample.read_bytes()
    assert entry["status"] == "ok"
