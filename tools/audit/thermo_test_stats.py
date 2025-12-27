import json
from pathlib import Path

DATA = {
    "component": "thermo",
    "version": "0.1.0",
    "collected_tests_count": 54,
    "test_files": [
        "tests/runtime/test_thermo_agent_bridge.py",
        "tests/sandbox/test_thermo_prototype.py",
        "tests/test_thermo_audit.py",
        "tests/test_thermo_fallback.py",
        "tests/test_thermo_hpc_ai.py",
        "tests/test_thermo_manual_override.py",
        "tests/test_thermo_optimizations.py",
        "tests/test_thermo_violations.py",
    ],
    # Fixed to the last verified collection time to avoid churn across runs.
    "last_run_timestamp": "2025-12-22T18:15:13.159607+00:00",
}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "docs" / "_generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "thermo_stats.json"
    serialized = json.dumps(DATA, indent=2)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
