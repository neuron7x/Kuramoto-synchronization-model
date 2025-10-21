from __future__ import annotations

from pathlib import Path

from tools.codegen.runtime.publisher import Artifact, ArtifactPublisher


def test_artifact_publisher_creates_versioned_directory(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    artifact_path = tmp_path / "output.py"
    artifact_path.write_text("print('hello')\n", encoding="utf-8")

    publisher = ArtifactPublisher(root, "1.2.3")
    published_path = publisher.publish("sample-task", [Artifact("sample", artifact_path)])

    expected_file = published_path / artifact_path.name
    assert expected_file.exists()
    manifest = (published_path / "MANIFEST.sha256").read_text(encoding="utf-8")
    assert manifest
