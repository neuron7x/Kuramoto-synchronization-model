"""Tests for docker-compose smoke test script."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# Import the module functions we want to test
from scripts.deploy.docker_compose_smoke import _create_smoke_env_file, _cleanup_env_file


def test_create_smoke_env_file_creates_file_with_defaults():
    """Test that _create_smoke_env_file creates a file with default values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.smoke"
        
        _create_smoke_env_file(env_path)
        
        assert env_path.exists()
        content = env_path.read_text()
        assert "POSTGRES_USER=tradepulse" in content
        assert "POSTGRES_PASSWORD=tradepulse_dev" in content
        assert "POSTGRES_DB=tradepulse" in content
        assert "TRADEPULSE_ENV=ci" in content
        assert "TRADEPULSE_HTTP_PORT=8000" in content


def test_create_smoke_env_file_respects_env_vars(monkeypatch):
    """Test that _create_smoke_env_file respects environment variables."""
    monkeypatch.setenv("POSTGRES_USER", "custom_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "custom_pass")
    monkeypatch.setenv("POSTGRES_DB", "custom_db")
    monkeypatch.setenv("TRADEPULSE_ENV", "production")
    monkeypatch.setenv("TRADEPULSE_HTTP_PORT", "9000")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.smoke"
        
        _create_smoke_env_file(env_path)
        
        assert env_path.exists()
        content = env_path.read_text()
        assert "POSTGRES_USER=custom_user" in content
        assert "POSTGRES_PASSWORD=custom_pass" in content
        assert "POSTGRES_DB=custom_db" in content
        assert "TRADEPULSE_ENV=production" in content
        assert "TRADEPULSE_HTTP_PORT=9000" in content


def test_cleanup_env_file_removes_existing_file():
    """Test that _cleanup_env_file removes an existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.smoke"
        env_path.write_text("test content")
        
        assert env_path.exists()
        _cleanup_env_file(env_path)
        assert not env_path.exists()


def test_cleanup_env_file_handles_nonexistent_file():
    """Test that _cleanup_env_file gracefully handles nonexistent files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env.smoke"
        
        # Should not raise an exception
        _cleanup_env_file(env_path)
        assert not env_path.exists()
