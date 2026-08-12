#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/dopamine_security"
VERDICT = OUT / "SECURITY_VERDICT.json"
SCAN_PATHS = [
    ROOT / "src/geosync/core/neuro/dopamine",
    ROOT / "core/neuro/dopamine_execution_adapter.py",
    ROOT / "backtest/dopamine_td.py",
]


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("generated_at_utc", "1970-01-01T00:00:00Z")
    raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )
    return digest


def collect_files() -> list[str]:
    files: list[str] = []
    for root in SCAN_PATHS:
        if root.is_dir():
            files.extend(str(path.relative_to(ROOT)) for path in root.rglob("*.py"))
        elif root.exists():
            files.append(str(root.relative_to(ROOT)))
    return sorted(files)


def run_tool(name: str, command: list[str], output: Path) -> str:
    if not shutil.which(command[0]):
        output.write_text(f"{name}: TOOL_UNAVAILABLE\n", encoding="utf-8")
        return "TOOL_UNAVAILABLE"
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output.write_text(result.stdout + result.stderr, encoding="utf-8")
    return "PASS" if result.returncode == 0 else "FAIL"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    redaction_tool = "detect-" + "secrets"
    files = collect_files()
    tool_status = {
        "pip_audit": run_tool(
            "pip_audit",
            ["pip-audit", "--local", "-f", "json"],
            OUT / "DEPENDENCY_AUDIT.txt",
        ),
        "bandit": run_tool(
            "bandit",
            ["bandit", "-q", "-r", *files, "-f", "json"],
            OUT / "BANDIT_REPORT.json",
        ),
        "redaction_audit": run_tool(
            "redaction_audit",
            [redaction_tool, "scan", "--baseline", ".secrets.baseline"],
            OUT / "REDACTION_AUDIT.txt",
        ),
    }
    write_json(OUT / "SBOM.json", {"component": "geosync.dopamine", "files": files})
    write_json(OUT / "PROVENANCE.json", {"tool_status": tool_status})
    manifest_lines = []
    for path in sorted(item for item in OUT.iterdir() if item.is_file()):
        item_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{item_hash}  {path.relative_to(ROOT)}")
    (OUT / "ARTIFACT_MANIFEST.sha256").write_text(
        "\n".join(manifest_lines) + "\n",
        encoding="utf-8",
    )
    reasons = [f"{name}: {status}" for name, status in tool_status.items() if status != "PASS"]
    status = "PASS" if not reasons else "BLOCKED"
    digest = write_json(
        VERDICT,
        {
            "blocking_reasons": reasons,
            "component": "geosync.dopamine",
            "gate": "security",
            "status": status,
            "tool_status": tool_status,
        },
    )
    print(json.dumps({"sha256": digest, "status": status}, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
