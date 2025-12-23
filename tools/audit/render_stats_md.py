import json
from pathlib import Path
from typing import Any, Dict, List


def _load_stats(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing stats file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _render_markdown(title: str, data: Dict[str, Any], destination: Path) -> None:
    lines: List[str] = [
        f"# {title}",
        "",
        f"- Version: `{data['version']}`",
        f"- Collected tests: {data['collected_tests_count']}",
        f"- Last collection timestamp: {data['last_run_timestamp']}",
        "- Test files:",
    ]
    for path in data["test_files"]:
        lines.append(f"  - `{path}`")

    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    generated_dir = repo_root / "docs" / "_generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    serotonin_data = _load_stats(generated_dir / "serotonin_stats.json")
    thermo_data = _load_stats(generated_dir / "thermo_stats.json")

    _render_markdown(
        "Serotonin Test Stats", serotonin_data, generated_dir / "serotonin_stats.md"
    )
    _render_markdown(
        "Thermo Test Stats", thermo_data, generated_dir / "thermo_stats.md"
    )


if __name__ == "__main__":
    main()
