# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for path validation utilities."""

import os
import tempfile

import pytest

from core.utils.path_validation import (
    PathTraversalError,
    ensure_directory_exists,
    sanitize_filename,
    validate_file_path,
    validate_safe_path,
)


class TestValidateSafePath:
    """Tests for validate_safe_path function."""

    def test_valid_relative_path(self, tmp_path):
        """Test validation of valid relative path."""
        result = validate_safe_path("data/file.csv", tmp_path)
        assert result == tmp_path / "data" / "file.csv"

    def test_path_traversal_blocked(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        with pytest.raises(PathTraversalError):
            validate_safe_path("../etc/passwd", tmp_path)

    def test_path_traversal_with_dots_blocked(self, tmp_path):
        """Test that path traversal with .. in path is blocked."""
        with pytest.raises(PathTraversalError):
            validate_safe_path("data/../../etc/passwd", tmp_path)

    def test_absolute_path_blocked_by_default(self, tmp_path):
        """Test that absolute paths are blocked by default."""
        with pytest.raises(PathTraversalError):
            validate_safe_path("/etc/passwd", tmp_path)

    def test_absolute_path_allowed_when_enabled(self, tmp_path):
        """Test that absolute paths can be allowed."""
        # Create a safe absolute path within tmp_path
        safe_path = tmp_path / "safe"
        safe_path.mkdir(exist_ok=True)

        result = validate_safe_path(safe_path, tmp_path, allow_absolute=True)
        assert result == safe_path

    def test_empty_path_rejected(self, tmp_path):
        """Test that empty path is rejected."""
        with pytest.raises(ValueError):
            validate_safe_path("", tmp_path)

    def test_symlink_traversal_blocked(self, tmp_path):
        """Test that symlink path traversal is blocked."""
        # Create a symlink that points outside base_dir
        with tempfile.TemporaryDirectory() as other_dir:
            link = tmp_path / "link"
            if hasattr(os, "symlink"):  # symlink not available on all platforms
                try:
                    os.symlink(other_dir, link)
                    with pytest.raises(PathTraversalError):
                        validate_safe_path("link/../../../etc/passwd", tmp_path)
                except OSError:
                    pytest.skip("Symlink creation not supported")


class TestValidateFilePath:
    """Tests for validate_file_path function."""

    def test_valid_existing_file(self, tmp_path):
        """Test validation of existing file."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        # Use relative path from base_dir
        result = validate_file_path("test.csv", tmp_path)
        assert result == test_file

    def test_missing_file_error_when_required(self, tmp_path):
        """Test that missing file raises error when must_exist=True."""
        with pytest.raises(FileNotFoundError):
            validate_file_path("nonexistent.csv", tmp_path, must_exist=True)

    def test_missing_file_ok_when_not_required(self, tmp_path):
        """Test that missing file is ok when must_exist=False."""
        result = validate_file_path("newfile.csv", tmp_path, must_exist=False)
        assert result == tmp_path / "newfile.csv"

    def test_directory_rejected_as_file(self, tmp_path):
        """Test that directory is rejected when file is expected."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with pytest.raises(ValueError, match="not a file"):
            validate_file_path("subdir", tmp_path, must_exist=True)

    def test_extension_validation(self, tmp_path):
        """Test file extension validation."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        # Valid extension
        result = validate_file_path("test.csv", tmp_path, extensions=[".csv", ".json"])
        assert result == test_file

        # Invalid extension
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_file_path("test.csv", tmp_path, extensions=[".json", ".txt"])

    def test_extension_case_insensitive(self, tmp_path):
        """Test that extension validation is case-insensitive."""
        test_file = tmp_path / "test.CSV"
        test_file.write_text("data")

        result = validate_file_path("test.CSV", tmp_path, extensions=[".csv"])
        assert result == test_file


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_sanitize_path_traversal(self):
        """Test sanitization of path traversal attempt."""
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_sanitize_special_characters(self):
        """Test sanitization of special characters."""
        result = sanitize_filename("file<script>.txt")
        assert "<" not in result
        assert ">" not in result
        # Extension separator is preserved
        assert result == "file_script.txt"

    def test_sanitize_null_bytes(self):
        """Test sanitization of null bytes."""
        result = sanitize_filename("file\0name.txt")
        assert "\0" not in result

    def test_remove_dots(self):
        """Test removal of dots."""
        result = sanitize_filename("..file..")
        assert result == "file"

    def test_handle_empty_result(self):
        """Test that empty results get default name."""
        # Only dots and spaces result in empty string after sanitization
        assert sanitize_filename("   ") == "unnamed_file"
        # Dots are replaced then stripped, leaving empty
        assert sanitize_filename("...") == "unnamed_file"

    def test_empty_input_rejected(self):
        """Test that empty input is rejected."""
        with pytest.raises(ValueError):
            sanitize_filename("")

    def test_custom_replacement_character(self):
        """Test custom replacement character."""
        result = sanitize_filename("file/name", replacement="-")
        assert result == "file-name"


class TestEnsureDirectoryExists:
    """Tests for ensure_directory_exists function."""

    def test_create_new_directory(self, tmp_path):
        """Test creation of new directory."""
        new_dir = tmp_path / "new_dir"
        result = ensure_directory_exists("new_dir", tmp_path)

        assert result == new_dir
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_existing_directory_ok(self, tmp_path):
        """Test that existing directory is ok."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = ensure_directory_exists("existing", tmp_path)
        assert result == existing_dir

    def test_create_with_parents(self, tmp_path):
        """Test creation of nested directories."""
        nested_dir = tmp_path / "level1" / "level2" / "level3"
        result = ensure_directory_exists("level1/level2/level3", tmp_path, create_parents=True)

        assert result == nested_dir
        assert nested_dir.exists()
        assert nested_dir.is_dir()

    def test_path_is_file_error(self, tmp_path):
        """Test that error is raised if path exists but is a file."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("data")

        with pytest.raises(ValueError, match="not a directory"):
            ensure_directory_exists("file.txt", tmp_path)

    def test_path_traversal_blocked(self, tmp_path):
        """Test that path traversal is blocked."""
        with pytest.raises(PathTraversalError):
            ensure_directory_exists("../outside", tmp_path)
