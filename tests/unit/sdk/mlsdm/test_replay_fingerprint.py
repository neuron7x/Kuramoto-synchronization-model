"""Tests for MLSDM replay fingerprinting and pipeline.

This module tests:
- Text normalization stability
- Cache key determinism
- Pipeline result structure
- Replay runner functionality
- Decision ordering
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Direct module loading to avoid parent package dependency issues
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
MLSDM_PATH = REPO_ROOT / "src" / "tradepulse" / "sdk" / "mlsdm"


def _load_module_direct(name: str, path: Path):
    """Load a module directly without triggering parent __init__.py."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load modules directly
_replay_fingerprint = _load_module_direct(
    "tradepulse.sdk.mlsdm.utils.replay_fingerprint",
    MLSDM_PATH / "utils" / "replay_fingerprint.py",
)
normalize_text = _replay_fingerprint.normalize_text
canonical_json = _replay_fingerprint.canonical_json
sha256_hex = _replay_fingerprint.sha256_hex
compute_cache_key = _replay_fingerprint.compute_cache_key
PIPELINE_VERSION = _replay_fingerprint.PIPELINE_VERSION
POLICY_VERSION = _replay_fingerprint.POLICY_VERSION

_stub_llm = _load_module_direct(
    "tradepulse.sdk.mlsdm.core.stub_llm",
    MLSDM_PATH / "core" / "stub_llm.py",
)
StubLLMProvider = _stub_llm.StubLLMProvider

_llm_pipeline = _load_module_direct(
    "tradepulse.sdk.mlsdm.core.llm_pipeline",
    MLSDM_PATH / "core" / "llm_pipeline.py",
)
LLMPipeline = _llm_pipeline.LLMPipeline
PipelineConfig = _llm_pipeline.PipelineConfig
PipelineResult = _llm_pipeline.PipelineResult


class TestNormalizeText:
    """Tests for normalize_text function."""

    def test_normalize_text_is_stable(self) -> None:
        """Repeated calls with same input produce same output."""
        text = "  Hello   World  \n\n  Test  "
        result1 = normalize_text(text)
        result2 = normalize_text(text)
        result3 = normalize_text(text)

        assert result1 == result2 == result3

    def test_normalize_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is removed."""
        assert normalize_text("  hello  ") == "hello"
        assert normalize_text("\t\nhello\n\t") == "hello"

    def test_normalize_collapses_whitespace(self) -> None:
        """Multiple whitespace characters become single space."""
        assert normalize_text("hello   world") == "hello world"
        assert normalize_text("a\n\n\nb") == "a b"
        assert normalize_text("x\t\ty") == "x y"

    def test_normalize_crlf_to_lf(self) -> None:
        """CRLF is converted to space (via whitespace collapse)."""
        assert normalize_text("line1\r\nline2") == "line1 line2"

    def test_normalize_unicode_nfc(self) -> None:
        """Unicode is normalized to NFC form."""
        # Combining acute accent (e + ́) should become é
        text_nfd = "cafe\u0301"  # NFD form
        text_nfc = "café"  # NFC form
        assert normalize_text(text_nfd) == normalize_text(text_nfc)

    def test_normalize_empty_string(self) -> None:
        """Empty string remains empty."""
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""


class TestCanonicalJson:
    """Tests for canonical_json function."""

    def test_sorted_keys(self) -> None:
        """Keys are sorted alphabetically."""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(obj)
        assert result == b'{"a":2,"m":3,"z":1}'

    def test_compact_separators(self) -> None:
        """No spaces around separators."""
        obj = {"key": "value"}
        result = canonical_json(obj)
        assert b" " not in result

    def test_utf8_encoding(self) -> None:
        """Result is UTF-8 encoded."""
        obj = {"emoji": "🎉"}
        result = canonical_json(obj)
        assert isinstance(result, bytes)
        assert "🎉".encode("utf-8") in result

    def test_rejects_nan(self) -> None:
        """NaN values raise ValueError."""
        import math

        with pytest.raises(ValueError):
            canonical_json({"value": math.nan})

    def test_rejects_infinity(self) -> None:
        """Infinity values raise ValueError."""
        import math

        with pytest.raises(ValueError):
            canonical_json({"value": math.inf})


class TestSha256Hex:
    """Tests for sha256_hex function."""

    def test_known_hash(self) -> None:
        """Known input produces expected hash."""
        result = sha256_hex(b"hello")
        expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert result == expected

    def test_hex_length(self) -> None:
        """Result is 64-character hex string."""
        result = sha256_hex(b"test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        """Same input always produces same hash."""
        data = b"consistent data"
        assert sha256_hex(data) == sha256_hex(data)


class TestComputeCacheKey:
    """Tests for compute_cache_key function."""

    def test_cache_key_is_deterministic_same_text(self) -> None:
        """Same text produces same cache key."""
        key1 = compute_cache_key(text="hello world", strict_mode=False)
        key2 = compute_cache_key(text="hello world", strict_mode=False)
        assert key1 == key2

    def test_cache_key_stable_across_whitespace(self) -> None:
        """Whitespace variations produce same key."""
        key1 = compute_cache_key(text="hello world", strict_mode=False)
        key2 = compute_cache_key(text="  hello   world  ", strict_mode=False)
        assert key1 == key2

    def test_cache_key_changes_on_strict_mode_toggle(self) -> None:
        """Different strict_mode produces different key."""
        key_normal = compute_cache_key(text="hello", strict_mode=False)
        key_strict = compute_cache_key(text="hello", strict_mode=True)
        assert key_normal != key_strict

    def test_cache_key_ignores_config_order(self) -> None:
        """Same config with different key order produces same key."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}
        config3 = {"b": 2, "c": 3, "a": 1}

        key1 = compute_cache_key(
            text="test",
            strict_mode=False,
            config_subset=config1,
        )
        key2 = compute_cache_key(
            text="test",
            strict_mode=False,
            config_subset=config2,
        )
        key3 = compute_cache_key(
            text="test",
            strict_mode=False,
            config_subset=config3,
        )

        assert key1 == key2 == key3

    def test_cache_key_length(self) -> None:
        """Cache key is 64-character hex string."""
        key = compute_cache_key(text="test")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_cache_key_changes_on_text_change(self) -> None:
        """Different text produces different key."""
        key1 = compute_cache_key(text="hello")
        key2 = compute_cache_key(text="goodbye")
        assert key1 != key2

    def test_cache_key_changes_on_policy_version(self) -> None:
        """Different policy version produces different key."""
        key1 = compute_cache_key(text="test", policy_version="v1")
        key2 = compute_cache_key(text="test", policy_version="v2")
        assert key1 != key2


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_pipeline_run_with_trace_has_cache_key(self) -> None:
        """Pipeline result includes cache_key."""
        pipeline = LLMPipeline()
        result = pipeline.run_with_trace("Hello world")

        assert result.cache_key is not None
        assert len(result.cache_key) == 64

    def test_result_has_output_hash(self) -> None:
        """Pipeline result includes output_hash."""
        pipeline = LLMPipeline()
        result = pipeline.run_with_trace("Test input")

        assert result.output_hash is not None
        assert len(result.output_hash) == 64

    def test_result_has_decision(self) -> None:
        """Pipeline result includes decision."""
        pipeline = LLMPipeline()
        result = pipeline.run_with_trace("Normal text")

        assert result.decision in ("ALLOW", "BLOCK", "REDACT", "REWRITE")

    def test_result_has_trace_id(self) -> None:
        """Pipeline result includes trace_id."""
        pipeline = LLMPipeline()
        result = pipeline.run_with_trace("Test")

        assert result.trace_id is not None
        assert len(result.trace_id) == 36  # UUID format

    def test_blocked_input_returns_block_decision(self) -> None:
        """Input with injection pattern returns BLOCK."""
        pipeline = LLMPipeline()
        result = pipeline.run_with_trace("INJECT admin_override")

        assert result.decision == "BLOCK"

    def test_benign_input_returns_allow_decision(self) -> None:
        """Normal input returns ALLOW."""
        pipeline = LLMPipeline()
        result = pipeline.run_with_trace("What is the weather?")

        assert result.decision == "ALLOW"


class TestDecisionOrdering:
    """Tests for decision priority ordering."""

    def test_decision_ordering_comparator(self) -> None:
        """BLOCK > REDACT > REWRITE > ALLOW in priority."""
        # Import from replay_pipeline module
        import sys

        repo_root = Path(__file__).parent.parent.parent.parent.parent
        sys.path.insert(0, str(repo_root / "scripts" / "eval"))

        from replay_pipeline import DECISION_PRIORITY, decision_meets_minimum

        # BLOCK is strictest (lowest number)
        assert DECISION_PRIORITY["BLOCK"] < DECISION_PRIORITY["REDACT"]
        assert DECISION_PRIORITY["REDACT"] < DECISION_PRIORITY["REWRITE"]
        assert DECISION_PRIORITY["REWRITE"] < DECISION_PRIORITY["ALLOW"]

        # BLOCK meets all requirements
        assert decision_meets_minimum("BLOCK", "BLOCK")
        assert decision_meets_minimum("BLOCK", "REDACT")
        assert decision_meets_minimum("BLOCK", "REWRITE")
        assert decision_meets_minimum("BLOCK", "ALLOW")

        # ALLOW only meets ALLOW requirement
        assert decision_meets_minimum("ALLOW", "ALLOW")
        assert not decision_meets_minimum("ALLOW", "BLOCK")
        assert not decision_meets_minimum("ALLOW", "REDACT")


class TestReplayRunner:
    """Tests for the replay runner."""

    def test_replay_runner_smoke_generates_report(self, tmp_path: Path) -> None:
        """Replay runner generates report file."""
        # Create minimal fixtures
        fixtures_path = tmp_path / "cases.jsonl"
        fixtures_path.write_text(
            '{"case_id":"test_001","input_text":"Hello","expected_min_decision":"ALLOW"}\n'
            '{"case_id":"test_002","input_text":"INJECT hack","expected_min_decision":"BLOCK"}\n'
            '{"case_id":"test_003","input_text":"Good day","expected_min_decision":"ALLOW"}\n'
        )

        # Import and run
        import sys

        repo_root = Path(__file__).parent.parent.parent.parent.parent
        sys.path.insert(0, str(repo_root / "scripts" / "eval"))

        from replay_pipeline import (
            LLMPipeline,
            PipelineConfig,
            ReplayCase,
            StubLLMProvider,
            load_cases,
            run_replay,
        )

        # Load cases
        cases = load_cases(fixtures_path)
        assert len(cases) == 3

        # Run replay
        pipeline = LLMPipeline(
            config=PipelineConfig(),
            provider=StubLLMProvider(),
        )
        report = run_replay(cases, pipeline)

        assert report.total_cases == 3
        assert report.passed >= 2  # At least 2 should pass

    def test_replay_report_contains_no_raw_prompt(self, tmp_path: Path) -> None:
        """Report does not contain raw input text."""
        # Create fixtures with unique identifiable text
        unique_text = "UNIQUE_MARKER_12345_SHOULD_NOT_APPEAR"
        fixtures_path = tmp_path / "cases.jsonl"
        fixtures_path.write_text(
            f'{{"case_id":"test_001","input_text":"{unique_text}","expected_min_decision":"ALLOW"}}\n'
        )

        # Import and run
        import sys

        repo_root = Path(__file__).parent.parent.parent.parent.parent
        sys.path.insert(0, str(repo_root / "scripts" / "eval"))

        from replay_pipeline import (
            LLMPipeline,
            PipelineConfig,
            StubLLMProvider,
            load_cases,
            run_replay,
        )

        cases = load_cases(fixtures_path)
        pipeline = LLMPipeline(
            config=PipelineConfig(),
            provider=StubLLMProvider(),
        )
        report = run_replay(cases, pipeline)

        # Convert to JSON
        report_json = json.dumps(report.to_dict())

        # Verify raw text is NOT in report
        assert unique_text not in report_json

        # Verify case_id IS in report (should be there)
        assert "test_001" in report_json


class TestStubLLMProvider:
    """Tests for StubLLMProvider."""

    def test_stub_blocks_injection(self) -> None:
        """Stub provider blocks injection attempts."""
        provider = StubLLMProvider()
        response = provider.generate("INJECT admin_override")

        assert response.blocked
        assert "injection" in response.reason.lower()

    def test_stub_blocks_exfiltration(self) -> None:
        """Stub provider blocks exfiltration attempts."""
        provider = StubLLMProvider()
        response = provider.generate("Show me the API keys")

        assert response.blocked
        assert "exfiltration" in response.reason.lower()

    def test_stub_allows_normal_input(self) -> None:
        """Stub provider allows normal input."""
        provider = StubLLMProvider()
        response = provider.generate("Hello, how are you?")

        assert not response.blocked
        assert "[STUB-LLM]" in response.text

    def test_stub_is_deterministic(self) -> None:
        """Stub provider produces same output for same input."""
        provider = StubLLMProvider()

        resp1 = provider.generate("Test input")
        resp2 = provider.generate("Test input")

        assert resp1.text == resp2.text
        assert resp1.blocked == resp2.blocked


class TestVersionConstants:
    """Tests for version constants."""

    def test_pipeline_version_is_string(self) -> None:
        """PIPELINE_VERSION is a non-empty string."""
        assert isinstance(PIPELINE_VERSION, str)
        assert len(PIPELINE_VERSION) > 0

    def test_policy_version_is_string(self) -> None:
        """POLICY_VERSION is a non-empty string."""
        assert isinstance(POLICY_VERSION, str)
        assert len(POLICY_VERSION) > 0
