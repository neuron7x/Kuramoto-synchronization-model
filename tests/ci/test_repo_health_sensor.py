# SPDX-License-Identifier: MIT
"""Contract tests for the hierarchical repository-health sensor.

These pin the fail-closed law: worst-wins aggregation, no silent promotion
of UNKNOWN to healthy, and one machine-readable JSON state for the repo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "repo_health_sensor.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("repo_health_sensor", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass field annotations resolve on 3.12.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_api() -> None:
    m = _load()
    assert callable(m.collect)
    assert callable(m.payload)
    assert callable(m.main)
    assert callable(m.worst)


def test_worst_wins_precedence() -> None:
    m = _load()
    assert m.worst([m.OK, m.OK]) == m.OK
    assert m.worst([m.OK, m.WARN]) == m.WARN
    assert m.worst([m.WARN, m.UNKNOWN]) == m.UNKNOWN
    assert m.worst([m.UNKNOWN, m.RED]) == m.RED
    assert m.worst([m.OK, m.WARN, m.UNKNOWN, m.RED]) == m.RED


def test_empty_aggregation_is_unknown_not_ok() -> None:
    m = _load()
    assert m.worst([]) == m.UNKNOWN


def test_collect_returns_sections() -> None:
    m = _load()
    sections = m.collect(ROOT)
    assert sections
    names = {s.name for s in sections}
    assert {"mfn_surface", "reproducible_capsules", "package_entrypoints"} <= names


def test_payload_shape_and_rollup() -> None:
    m = _load()
    result = m.payload(m.collect(ROOT))
    assert set(result) == {"status", "counts", "sections"}
    assert result["status"] in {m.OK, m.WARN, m.RED, m.UNKNOWN}
    assert set(result["counts"]) == {m.OK, m.WARN, m.RED, m.UNKNOWN}
    # rollup total equals the sum of per-section counts
    total = sum(result["counts"].values())
    per_section = sum(sum(s["counts"].values()) for s in result["sections"])
    assert total == per_section


def test_overall_status_is_worst_of_sections() -> None:
    m = _load()
    sections = m.collect(ROOT)
    result = m.payload(sections)
    assert result["status"] == m.worst([s.status for s in sections])


def test_entrypoints_resolve_on_this_repo() -> None:
    m = _load()
    section = m.package_entrypoints(ROOT)
    # the declared console scripts must point at modules that exist
    reds = [r for r in section.rows if r.status == m.RED]
    assert not reds, f"unresolved entrypoints: {[r.path for r in reds]}"


def test_main_runs_and_emits_json(capsys) -> None:
    import json

    m = _load()
    rc = m.main(["--root", str(ROOT)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "status" in data and "sections" in data
    assert rc in (0, 1)
