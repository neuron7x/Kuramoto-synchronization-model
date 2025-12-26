from __future__ import annotations

import sys

from application.runtime import server


def test_main_wires_cli_arguments(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(*, config_path=None, cli_overrides=None) -> None:
        captured["config_path"] = config_path
        captured["cli_overrides"] = cli_overrides

    monkeypatch.setattr(server, "run", fake_run)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tradepulse-server",
            "--config",
            "/tmp/config.yaml",
            "--host",
            "0.0.0.0",
            "--port",
            "12345",
            "--allow-plaintext",
            "--serotonin-config",
            "/tmp/serotonin.yaml",
            "--thermo-config",
            "/tmp/thermo.yaml",
            "--dry-run",
            "--health",
        ],
    )

    server.main()

    assert captured["config_path"] == "/tmp/config.yaml"
    assert captured["cli_overrides"] == {
        "host": "0.0.0.0",
        "port": 12345,
        "allow_plaintext": True,
        "serotonin_config": "/tmp/serotonin.yaml",
        "thermo_config": "/tmp/thermo.yaml",
        "dry_run": True,
        "health": True,
    }
