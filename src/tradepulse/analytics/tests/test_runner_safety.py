"""Tests for safety helpers in :mod:`analytics.runner`."""

from __future__ import annotations

from omegaconf import OmegaConf

from analytics import runner


def test_redact_sensitive_data_masks_known_keys() -> None:
    """Sensitive keys should be masked while others remain intact."""

    original = {
        "database": {"user": "analyst", "password": "super-secret"},
        "apiKey": "plaintext-key",
        "nested": {"client-secret": "needs-masking", "normal": "value"},
        "monkey": "should-remain-visible",
        "author": "jane",  # should not be treated as auth credentials
        "sequence": [
            {"token": "token-value"},
            {"keep": "visible"},
        ],
    }

    redacted = runner._redact_sensitive_data(original)

    assert redacted["database"]["password"] == runner.REDACTED_PLACEHOLDER
    assert redacted["database"]["user"] == "analyst"
    assert redacted["apiKey"] == runner.REDACTED_PLACEHOLDER
    assert redacted["nested"]["client-secret"] == runner.REDACTED_PLACEHOLDER
    assert redacted["nested"]["normal"] == "value"
    assert redacted["sequence"][0]["token"] == runner.REDACTED_PLACEHOLDER
    assert redacted["sequence"][1]["keep"] == "visible"
    assert redacted["monkey"] == "should-remain-visible"
    assert redacted["author"] == "jane"

    # The original mapping should not be mutated.
    assert original["database"]["password"] == "super-secret"
    assert original["apiKey"] == "plaintext-key"


def test_redacted_config_yaml_masks_sensitive_values() -> None:
    """Rendered YAML output must not expose sensitive literals."""

    # Use a benign non-URL sentinel for the endpoint so static analysis does not
    # flag the fixture as an unsanitized URL while still exercising the
    # redaction behaviour for non-sensitive values.
    cfg = OmegaConf.create(
        {
            "auth": {"token": "should-not-leak"},
            "service": {"endpoint": "analytics-endpoint", "timeout": 10},
        }
    )

    rendered = runner._redacted_config_yaml(cfg)

    assert "should-not-leak" not in rendered
    assert runner.REDACTED_PLACEHOLDER in rendered
    assert "analytics-endpoint" in rendered


def test_redacted_config_yaml_handles_unresolved_interpolations() -> None:
    """Interpolation placeholders should remain intact instead of erroring."""

    cfg = OmegaConf.create(
        {
            "paths": {
                "base": "${hydra.run.dir}",
                "artifact": "${paths.base}/artifact.bin",
            },
            "credentials": {"api_key": "top-secret"},
        }
    )

    rendered = runner._redacted_config_yaml(cfg)

    assert "${hydra.run.dir}" in rendered
    assert runner.REDACTED_PLACEHOLDER in rendered
    assert "artifact.bin" in rendered
