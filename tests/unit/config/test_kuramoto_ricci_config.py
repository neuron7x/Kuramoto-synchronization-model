# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from core.config import (
    ConfigError,
    KuramotoRicciIntegrationConfig,
    TradePulseSettings,
    YamlSettingsSource,
    export_tradepulse_settings_schema,
    load_kuramoto_ricci_config,
    parse_cli_overrides,
)
from core.config.kuramoto_ricci import SettingsError
from core.indicators.multiscale_kuramoto import TimeFrame


def test_loader_returns_defaults_when_file_missing() -> None:
    cfg = load_kuramoto_ricci_config("does-not-exist.yaml")
    engine_kwargs = cfg.to_engine_kwargs()

    assert engine_kwargs["kuramoto_config"]["base_window"] == 200
    assert engine_kwargs["ricci_config"]["window_size"] == 100
    assert engine_kwargs["composite_config"]["R_strong_emergent"] == 0.8


def test_loader_reads_yaml_values() -> None:
    payload = {
        "kuramoto": {
            "timeframes": ["M1", "M5"],
            "adaptive_window": {"enabled": False, "base_window": 128},
            "min_samples_per_scale": 32,
        },
        "ricci": {
            "temporal": {"window_size": 150, "n_snapshots": 5, "retain_history": False},
            "graph": {"n_levels": 12, "connection_threshold": 0.2},
        },
        "composite": {
            "thresholds": {
                "R_strong_emergent": 0.9,
                "R_proto_emergent": 0.5,
                "coherence_min": 0.7,
            },
            "signals": {"min_confidence": 0.65},
        },
    }

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(yaml.safe_dump(payload))
        cfg = KuramotoRicciIntegrationConfig.from_file(path)

    engine_kwargs = cfg.to_engine_kwargs()
    kuramoto = engine_kwargs["kuramoto_config"]
    ricci = engine_kwargs["ricci_config"]
    composite = engine_kwargs["composite_config"]

    assert kuramoto["timeframes"] == (TimeFrame.M1, TimeFrame.M5)
    assert kuramoto["use_adaptive_window"] is False
    assert kuramoto["base_window"] == 128
    assert kuramoto["min_samples_per_scale"] == 32

    assert ricci["window_size"] == 150
    assert ricci["n_snapshots"] == 5
    assert ricci["retain_history"] is False
    assert ricci["connection_threshold"] == pytest.approx(0.2)

    assert composite["R_strong_emergent"] == 0.9
    assert composite["coherence_threshold"] == 0.7
    assert composite["min_confidence"] == pytest.approx(0.65)


def test_invalid_thresholds_raise_error() -> None:
    payload = {
        "composite": {
            "thresholds": {"R_proto_emergent": 0.8, "R_strong_emergent": 0.7}
        },
    }

    with pytest.raises(ConfigError):
        KuramotoRicciIntegrationConfig.from_mapping(payload)


def test_parse_cli_overrides_supports_nested_assignments() -> None:
    overrides = parse_cli_overrides(
        [
            "kuramoto.base_window=128",
            "composite.thresholds.R_strong_emergent=0.9",
            "kuramoto.timeframes=['M1','M5']",
        ]
    )

    assert overrides["kuramoto"]["base_window"] == 128
    assert overrides["composite"]["thresholds"]["R_strong_emergent"] == 0.9
    assert overrides["kuramoto"]["timeframes"] == ["M1", "M5"]


def test_settings_source_priority(monkeypatch, tmp_path) -> None:
    yaml_payload = {"kuramoto": {"base_window": 128}}
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(yaml.safe_dump(yaml_payload))

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("TRADEPULSE_KURAMOTO__BASE_WINDOW=256\n", encoding="utf8")

    monkeypatch.chdir(tmp_path)

    # .env should override YAML
    cfg_from_dotenv = load_kuramoto_ricci_config(yaml_path)
    assert cfg_from_dotenv.kuramoto.base_window == 256

    # Environment variables take precedence over .env
    monkeypatch.setenv("TRADEPULSE_KURAMOTO__BASE_WINDOW", "384")
    cfg_from_env = load_kuramoto_ricci_config(yaml_path)
    assert cfg_from_env.kuramoto.base_window == 384

    # CLI overrides win over environment variables
    cfg_from_cli = load_kuramoto_ricci_config(
        yaml_path,
        cli_overrides={"kuramoto": {"base_window": 512}},
    )
    assert cfg_from_cli.kuramoto.base_window == 512

    # Removing env sources falls back to YAML defaults
    monkeypatch.delenv("TRADEPULSE_KURAMOTO__BASE_WINDOW", raising=False)
    dotenv_path.unlink()
    cfg_from_yaml = load_kuramoto_ricci_config(yaml_path)
    assert cfg_from_yaml.kuramoto.base_window == 128


def test_parse_cli_overrides_rejects_missing_assignment() -> None:
    with pytest.raises(ConfigError, match="key=value"):
        parse_cli_overrides(["kuramoto.base_window"])


def test_parse_cli_overrides_rejects_empty_key() -> None:
    with pytest.raises(ConfigError, match="cannot be empty"):
        parse_cli_overrides(["=42"])


def test_parse_cli_overrides_detects_path_collision() -> None:
    with pytest.raises(ConfigError, match="collides"):
        parse_cli_overrides(["kuramoto=1", "kuramoto.timeframes=['M1']"])


class _StubSource:
    def __init__(self, payload: dict[str, object]):
        self._payload = dict(payload)

    def __call__(self) -> dict[str, object]:
        return dict(self._payload)


def test_yaml_settings_source_uses_default_file() -> None:
    source = YamlSettingsSource(
        TradePulseSettings,
        _StubSource({}),
        _StubSource({}),
        _StubSource({}),
    )

    payload = source()
    assert "kuramoto" in payload and "ricci" in payload


def test_yaml_settings_source_reads_cli_override_path(tmp_path: Path) -> None:
    config_path = tmp_path / "custom.yaml"
    config_path.write_text(yaml.safe_dump({"kuramoto": {"base_window": 321}}))

    source = YamlSettingsSource(
        TradePulseSettings,
        _StubSource({"config_file": str(config_path)}),
        _StubSource({}),
        _StubSource({}),
    )

    payload = source()
    assert payload["kuramoto"]["base_window"] == 321


def test_yaml_settings_source_rejects_non_mapping_payload(tmp_path: Path) -> None:
    config_path = tmp_path / "list.yaml"
    config_path.write_text(yaml.safe_dump([1, 2, 3]))

    source = YamlSettingsSource(
        TradePulseSettings,
        _StubSource({"config_file": str(config_path)}),
        _StubSource({}),
        _StubSource({}),
    )

    with pytest.raises(SettingsError, match="must define a mapping"):
        source()


def test_yaml_settings_source_surfaces_yaml_parse_errors(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text("invalid: [unterminated")

    source = YamlSettingsSource(
        TradePulseSettings,
        _StubSource({"config_file": str(broken_path)}),
        _StubSource({}),
        _StubSource({}),
    )

    with pytest.raises(SettingsError, match="failed to parse YAML"):
        source()


def test_export_tradepulse_schema_writes_file(tmp_path: Path) -> None:
    destination = tmp_path / "tradepulse-schema.json"
    schema = export_tradepulse_settings_schema(destination, indent=4)

    assert destination.exists()
    parsed = json.loads(destination.read_text(encoding="utf8"))
    assert parsed["title"] == "TradePulseSettings"
    assert schema == parsed


def test_export_tradepulse_schema_returns_payload_without_writing() -> None:
    schema = export_tradepulse_settings_schema(None)

    assert "properties" in schema
    assert "kuramoto" in schema["properties"]
