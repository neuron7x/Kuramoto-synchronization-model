"""Negative security-focused tests for :class:`PromptSanitizer`."""

from __future__ import annotations

import pytest

from core.agent.prompting import PromptInjectionDetected, PromptSanitizer


@pytest.fixture()
def sanitizer() -> PromptSanitizer:
    return PromptSanitizer()


def test_sql_injection_payload_is_rejected(sanitizer: PromptSanitizer) -> None:
    payload = "1; DROP TABLE users; --"
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(payload)
    assert str(excinfo.value) == "input appears to contain a SQL injection payload"


def test_xss_vectors_are_blocked(sanitizer: PromptSanitizer) -> None:
    payload = "<img src=x onerror=alert('owned')>"
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(payload)
    assert str(excinfo.value) == "possible cross-site scripting content detected"


def test_csrf_form_post_is_rejected(sanitizer: PromptSanitizer) -> None:
    payload = (
        '<form action="https://evil.example/transfer" method="post">'
        "<input name='amount' value='1000'>"
    )
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(payload)
    assert str(excinfo.value) == "input resembles a cross-site request forgery payload"


def test_unsafe_deserialization_patterns_raise(sanitizer: PromptSanitizer) -> None:
    payload = "pickle.loads(__import__('os').system('id'))"
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(payload)
    assert str(excinfo.value) == "unsafe dynamic deserialization directive detected"


def test_xml_entity_expansion_is_detected(sanitizer: PromptSanitizer) -> None:
    payload = "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(payload)
    assert (
        str(excinfo.value)
        == "input includes XML entity declarations that can trigger entity expansion"
    )


def test_path_traversal_sequences_trigger_guardrails(
    sanitizer: PromptSanitizer,
) -> None:
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text("../../secrets/creds.yml")
    assert str(excinfo.value) == "path traversal sequence detected in input"


def test_length_guard_blocks_potential_overflow() -> None:
    local_sanitizer = PromptSanitizer(max_length=16)
    with pytest.raises(PromptInjectionDetected) as excinfo:
        local_sanitizer.sanitize_text("A" * 17)
    assert str(excinfo.value) == "input exceeds maximum supported length"


def test_binary_payloads_are_rejected(sanitizer: PromptSanitizer) -> None:
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(b"\x00\x01\x02")
    assert str(excinfo.value) == "binary payloads are not permitted"


def test_unexpected_encoding_sequences_are_flagged(sanitizer: PromptSanitizer) -> None:
    malformed = b"\xed\xb3\xbf".decode("utf-8", "surrogatepass")
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text(malformed)
    assert str(excinfo.value) == "input must be valid UTF-8 text"


def test_locale_override_attempts_are_detected(sanitizer: PromptSanitizer) -> None:
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_text("LC_ALL=fr_FR.UTF-8; LANG=fr_FR")
    assert str(excinfo.value) == "locale override directives are not permitted"


def test_unicode_input_is_normalised(sanitizer: PromptSanitizer) -> None:
    composed = "é"
    decomposed = "e\u0301"
    assert sanitizer.sanitize_text(decomposed) == composed


def test_sanitize_mapping_enforces_non_empty_keys(sanitizer: PromptSanitizer) -> None:
    with pytest.raises(PromptInjectionDetected) as excinfo:
        sanitizer.sanitize_mapping({"  ": "value"})
    assert str(excinfo.value) == "parameter names must be non-empty strings"


def test_sanitize_mapping_trims_keys(sanitizer: PromptSanitizer) -> None:
    mapping = {"  symbol  ": "AAPL"}
    sanitized = sanitizer.sanitize_mapping(mapping)
    assert sanitized == {"symbol": "AAPL"}
