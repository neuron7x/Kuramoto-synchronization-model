# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for core.versioning module - build metadata and config provenance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.versioning import (
    BuildMetadata,
    ConfigProvenance,
    GitInfo,
    compute_config_hash,
    create_config_provenance,
    get_build_metadata,
    get_git_info,
    get_package_version,
    load_provenance,
    save_provenance,
    verify_config_hash,
)


class TestGitInfo:
    """Tests for GitInfo dataclass."""

    def test_creation(self) -> None:
        """GitInfo should accept all fields."""
        now = datetime.now(timezone.utc)
        info = GitInfo(
            commit="abc123def456",
            short_commit="abc123d",
            branch="main",
            tag="v1.0.0",
            dirty=False,
            commit_date=now,
        )
        assert info.commit == "abc123def456"
        assert info.short_commit == "abc123d"
        assert info.branch == "main"
        assert info.tag == "v1.0.0"
        assert info.dirty is False
        assert info.commit_date == now

    def test_to_dict(self) -> None:
        """GitInfo.to_dict should serialize correctly."""
        now = datetime.now(timezone.utc)
        info = GitInfo(
            commit="abc123",
            short_commit="abc",
            branch="feature",
            tag=None,
            dirty=True,
            commit_date=now,
        )
        result = info.to_dict()
        assert result["commit"] == "abc123"
        assert result["branch"] == "feature"
        assert result["tag"] is None
        assert result["dirty"] is True
        assert result["commit_date"] == now.isoformat()

    def test_to_dict_no_date(self) -> None:
        """to_dict should handle None commit_date."""
        info = GitInfo(
            commit="abc",
            short_commit="a",
            branch=None,
            tag=None,
            dirty=False,
            commit_date=None,
        )
        result = info.to_dict()
        assert result["commit_date"] is None


class TestBuildMetadata:
    """Tests for BuildMetadata dataclass."""

    def test_creation(self) -> None:
        """BuildMetadata should accept all fields."""
        now = datetime.now(timezone.utc)
        git_info = GitInfo(
            commit="abc",
            short_commit="a",
            branch="main",
            tag=None,
            dirty=False,
            commit_date=now,
        )
        metadata = BuildMetadata(
            version="1.2.3",
            git=git_info,
            python_version="3.11.0",
            platform="Linux-x86_64",
            build_time=now,
            environment="prod",
        )
        assert metadata.version == "1.2.3"
        assert metadata.git == git_info
        assert metadata.environment == "prod"

    def test_to_dict(self) -> None:
        """BuildMetadata.to_dict should serialize correctly."""
        now = datetime.now(timezone.utc)
        metadata = BuildMetadata(
            version="1.0.0",
            git=None,
            python_version="3.11",
            platform="Linux",
            build_time=now,
        )
        result = metadata.to_dict()
        assert result["version"] == "1.0.0"
        assert result["git"] is None
        assert result["python_version"] == "3.11"
        assert "build_time" in result

    def test_to_json(self) -> None:
        """BuildMetadata.to_json should produce valid JSON."""
        now = datetime.now(timezone.utc)
        metadata = BuildMetadata(
            version="1.0.0",
            git=None,
            python_version="3.11",
            platform="Linux",
            build_time=now,
        )
        json_str = metadata.to_json()
        parsed = json.loads(json_str)
        assert parsed["version"] == "1.0.0"


class TestGetPackageVersion:
    """Tests for get_package_version function."""

    def test_returns_string(self) -> None:
        """get_package_version should return a string."""
        version = get_package_version()
        assert isinstance(version, str)
        assert len(version) > 0


class TestGetGitInfo:
    """Tests for get_git_info function."""

    def test_in_git_repo(self) -> None:
        """get_git_info should return info when in a git repo."""
        # We're in the TradePulse repo, so this should work
        info = get_git_info()
        if info is not None:
            assert len(info.commit) >= 7
            assert len(info.short_commit) == 7
            assert isinstance(info.dirty, bool)

    def test_non_git_directory(self, tmp_path: Path) -> None:
        """get_git_info should return None for non-git directories."""
        info = get_git_info(tmp_path)
        assert info is None


class TestGetBuildMetadata:
    """Tests for get_build_metadata function."""

    def test_returns_metadata(self) -> None:
        """get_build_metadata should return BuildMetadata."""
        metadata = get_build_metadata()
        assert isinstance(metadata, BuildMetadata)
        assert len(metadata.version) > 0
        assert len(metadata.python_version) > 0
        assert len(metadata.platform) > 0

    def test_with_environment(self) -> None:
        """get_build_metadata should accept environment."""
        metadata = get_build_metadata(environment="staging")
        assert metadata.environment == "staging"


class TestComputeConfigHash:
    """Tests for compute_config_hash function."""

    def test_deterministic(self) -> None:
        """compute_config_hash should be deterministic."""
        config = {"key": "value", "number": 42}
        hash1 = compute_config_hash(config)
        hash2 = compute_config_hash(config)
        assert hash1 == hash2

    def test_order_independent(self) -> None:
        """compute_config_hash should be order-independent."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}
        assert compute_config_hash(config1) == compute_config_hash(config2)

    def test_different_configs(self) -> None:
        """Different configs should have different hashes."""
        hash1 = compute_config_hash({"key": "value1"})
        hash2 = compute_config_hash({"key": "value2"})
        assert hash1 != hash2

    def test_nested_dicts(self) -> None:
        """compute_config_hash should handle nested dicts."""
        config = {
            "database": {"host": "localhost", "port": 5432},
            "cache": {"enabled": True},
        }
        hash1 = compute_config_hash(config)
        # Same config in different order
        config2 = {
            "cache": {"enabled": True},
            "database": {"port": 5432, "host": "localhost"},
        }
        hash2 = compute_config_hash(config2)
        assert hash1 == hash2

    def test_lists(self) -> None:
        """compute_config_hash should handle lists."""
        config = {"items": [1, 2, 3]}
        hash1 = compute_config_hash(config)
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_datetime(self) -> None:
        """compute_config_hash should handle datetime objects."""
        now = datetime.now(timezone.utc)
        config = {"timestamp": now}
        hash1 = compute_config_hash(config)
        assert len(hash1) == 64


class TestConfigProvenance:
    """Tests for ConfigProvenance dataclass."""

    def test_creation(self) -> None:
        """ConfigProvenance should accept all fields."""
        build = get_build_metadata()
        provenance = ConfigProvenance(
            config_hash="abc123",
            config_snapshot={"key": "value"},
            build=build,
        )
        assert provenance.config_hash == "abc123"
        assert provenance.config_snapshot["key"] == "value"
        assert provenance.build == build

    def test_to_dict(self) -> None:
        """ConfigProvenance.to_dict should serialize correctly."""
        build = get_build_metadata()
        provenance = ConfigProvenance(
            config_hash="abc123",
            config_snapshot={"db": "postgres"},
            build=build,
        )
        result = provenance.to_dict()
        assert result["config_hash"] == "abc123"
        assert result["config_snapshot"]["db"] == "postgres"
        assert "build" in result
        assert "timestamp" in result

    def test_to_json(self) -> None:
        """ConfigProvenance.to_json should produce valid JSON."""
        build = get_build_metadata()
        provenance = ConfigProvenance(
            config_hash="abc123",
            config_snapshot={},
            build=build,
        )
        json_str = provenance.to_json()
        parsed = json.loads(json_str)
        assert parsed["config_hash"] == "abc123"


class TestCreateConfigProvenance:
    """Tests for create_config_provenance function."""

    def test_creates_provenance(self) -> None:
        """create_config_provenance should create valid provenance."""
        config = {"database": {"host": "localhost"}}
        provenance = create_config_provenance(config)
        assert isinstance(provenance, ConfigProvenance)
        assert provenance.config_hash == compute_config_hash(config)
        assert provenance.config_snapshot == config

    def test_with_environment(self) -> None:
        """create_config_provenance should accept environment."""
        provenance = create_config_provenance({}, environment="test")
        assert provenance.build.environment == "test"


class TestSaveAndLoadProvenance:
    """Tests for save_provenance and load_provenance functions."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """save_provenance and load_provenance should roundtrip."""
        config = {"key": "value", "number": 42}
        original = create_config_provenance(config, environment="test")

        file_path = tmp_path / "provenance.json"
        save_provenance(original, file_path)

        loaded = load_provenance(file_path)
        assert loaded.config_hash == original.config_hash
        assert loaded.config_snapshot == original.config_snapshot
        assert loaded.build.version == original.build.version

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """load_provenance should raise for nonexistent files."""
        with pytest.raises(FileNotFoundError):
            load_provenance(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """load_provenance should raise for invalid JSON."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid provenance JSON"):
            load_provenance(file_path)

    def test_save_creates_directories(self, tmp_path: Path) -> None:
        """save_provenance should create parent directories."""
        provenance = create_config_provenance({})
        file_path = tmp_path / "nested" / "dir" / "provenance.json"
        save_provenance(provenance, file_path)
        assert file_path.exists()


class TestVerifyConfigHash:
    """Tests for verify_config_hash function."""

    def test_matching_hash(self) -> None:
        """verify_config_hash should return True for matching hash."""
        config = {"key": "value"}
        expected = compute_config_hash(config)
        assert verify_config_hash(config, expected) is True

    def test_non_matching_hash(self) -> None:
        """verify_config_hash should return False for non-matching hash."""
        config = {"key": "value"}
        assert verify_config_hash(config, "wrong_hash") is False

    def test_modified_config(self) -> None:
        """verify_config_hash should detect config changes."""
        original = {"key": "value"}
        expected = compute_config_hash(original)
        modified = {"key": "different"}
        assert verify_config_hash(modified, expected) is False
