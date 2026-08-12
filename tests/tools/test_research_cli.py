from __future__ import annotations

import json
from pathlib import Path

from tools.research.research_cli import main
from tools.research.validate_ricci_artifact_schema import validate_artifact


def test_research_run_creates_schema_valid_hypothesis_artifact(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    data = tmp_path / "data.json"
    out = tmp_path / "runs"
    config.write_text("input_window_sec: 30\n", encoding="utf-8")
    data.write_text('{"rows": []}\n', encoding="utf-8")

    exit_code = main([
        "run",
        "--line",
        "ricci_microstructure_v1",
        "--config",
        str(config),
        "--data",
        str(data),
        "--out",
        str(out),
    ])

    assert exit_code == 0
    artifact = out / "RFC-2026-MARKET-RICCI-V1" / "artifact.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["claim_tier"] == "HYPOTHESIS"
    assert payload["falsification_status"] == "NOT_RUN"
    assert payload["decision"] == "OBSERVE"
    assert (
        validate_artifact(Path("schemas/research/research_inference_artifact.schema.json"), artifact)
        == []
    )


def test_research_verify_accepts_run_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    source = Path("artifacts/runs/ricci_microstructure_v1/example_artifact.json")
    (run_dir / "artifact.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    assert main(["verify", str(run_dir)]) == 0


def test_research_run_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    data = tmp_path / "data.json"
    out = tmp_path / "runs"
    config.write_text("input_window_sec: 30\n", encoding="utf-8")
    data.write_text('{"rows": []}\n', encoding="utf-8")
    args = [
        "run",
        "--line",
        "ricci_microstructure_v1",
        "--config",
        str(config),
        "--data",
        str(data),
        "--out",
        str(out),
    ]

    assert main(args) == 0
    try:
        main(args)
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("second run unexpectedly overwrote artifact")

    assert main([*args, "--force"]) == 0


def test_research_run_rejects_bad_timestamp_before_write(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    data = tmp_path / "data.json"
    out = tmp_path / "runs"
    config.write_text("input_window_sec: 30\n", encoding="utf-8")
    data.write_text('{"rows": []}\n', encoding="utf-8")

    try:
        main([
            "run",
            "--line",
            "ricci_microstructure_v1",
            "--config",
            str(config),
            "--data",
            str(data),
            "--out",
            str(out),
            "--timestamp-utc",
            "bad-time",
        ])
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("bad timestamp unexpectedly accepted")

    assert not (out / "RFC-2026-MARKET-RICCI-V1" / "artifact.json").exists()


def test_research_run_rejects_symlinked_data_file(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    real_data = tmp_path / "real-data.json"
    data_link = tmp_path / "data-link.json"
    out = tmp_path / "runs"
    config.write_text("input_window_sec: 30\n", encoding="utf-8")
    real_data.write_text('{"rows": []}\n', encoding="utf-8")
    data_link.symlink_to(real_data)

    try:
        main([
            "run",
            "--line",
            "ricci_microstructure_v1",
            "--config",
            str(config),
            "--data",
            str(data_link),
            "--out",
            str(out),
        ])
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("symlinked data input unexpectedly accepted")

    assert not (out / "RFC-2026-MARKET-RICCI-V1" / "artifact.json").exists()


def test_research_run_rejects_symlink_inside_data_directory(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    real_data = tmp_path / "real-data.json"
    out = tmp_path / "runs"
    config.write_text("input_window_sec: 30\n", encoding="utf-8")
    data_dir.mkdir()
    real_data.write_text('{"rows": []}\n', encoding="utf-8")
    (data_dir / "safe.json").write_text('{"rows": []}\n', encoding="utf-8")
    (data_dir / "linked.json").symlink_to(real_data)

    try:
        main([
            "run",
            "--line",
            "ricci_microstructure_v1",
            "--config",
            str(config),
            "--data",
            str(data_dir),
            "--out",
            str(out),
        ])
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("symlinked directory member unexpectedly accepted")

    assert not (out / "RFC-2026-MARKET-RICCI-V1" / "artifact.json").exists()
