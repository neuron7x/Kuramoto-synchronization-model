import json
from pathlib import Path

DATA = {
    "component": "serotonin",
    "version": "2.4.0",
    "collected_tests_count": 188,
    "test_files": [
        "core/neuro/tests/test_serotonin_controller.py",
        "tests/core/neuro/serotonin/test_config_contract.py",
        "tests/core/neuro/serotonin/test_serotonin_controller.py",
        "tests/core/neuro/serotonin/test_serotonin_runtime_safety.py",
        "tests/unit/tradepulse/core/neuro/serotonin/test_fixes_standalone.py",
        "tests/unit/tradepulse/core/neuro/serotonin/test_observability.py",
        "tests/unit/tradepulse/core/neuro/serotonin/test_practical_utilities.py",
        "tests/unit/tradepulse/core/neuro/serotonin/test_serotonin_controller_simplified.py",
        "tests/unit/tradepulse/core/neuro/serotonin/test_state_persistence.py",
    ],
    # Fixed to the last verified collection time to avoid churn across runs.
    "last_run_timestamp": "2025-12-22T18:15:13.178607+00:00",
}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = repo_root / "docs" / "_generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "serotonin_stats.json"
    serialized = json.dumps(DATA, indent=2)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
