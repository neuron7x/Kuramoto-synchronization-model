# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Secure path validation utilities to prevent path traversal attacks.

This module provides functions to safely validate file paths and prevent
directory traversal vulnerabilities.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Union


class PathTraversalError(ValueError):
    """Raised when a path traversal attack is detected."""

    pass


def validate_safe_path(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    allow_absolute: bool = False,
) -> Path:
    """Validate that a path is safe and within the allowed base directory.

    This function prevents path traversal attacks by ensuring that the resolved
    path stays within the specified base directory.

    Args:
        path: The path to validate
        base_dir: The base directory that the path must be within
        allow_absolute: If True, allows absolute paths (still checked against base_dir)

    Returns:
        The validated, resolved path as a Path object

    Raises:
        PathTraversalError: If the path attempts to escape the base directory
        ValueError: If the path is invalid

    Examples:
        >>> validate_safe_path("data/file.csv", "/app/data")
        Path('/app/data/file.csv')

        >>> validate_safe_path("../etc/passwd", "/app/data")
        PathTraversalError: Path traversal detected
    """
    if not path:
        raise ValueError("Path cannot be empty")

    path = Path(path)
    base_dir = Path(base_dir).resolve()

    # Check for absolute paths if not allowed
    if not allow_absolute and path.is_absolute():
        raise PathTraversalError(f"Absolute paths are not allowed: {path}")

    # Resolve the full path
    if path.is_absolute():
        full_path = path.resolve()
    else:
        full_path = (base_dir / path).resolve()

    # Ensure the resolved path is within the base directory
    try:
        full_path.relative_to(base_dir)
    except ValueError as exc:
        raise PathTraversalError(
            f"Path traversal detected: '{path}' resolves outside '{base_dir}'"
        ) from exc

    return full_path


def validate_file_path(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    must_exist: bool = True,
    extensions: list[str] | None = None,
) -> Path:
    """Validate a file path with additional checks.

    Args:
        path: The file path to validate
        base_dir: The base directory that the path must be within
        must_exist: If True, the file must exist
        extensions: Optional list of allowed file extensions (e.g., ['.csv', '.json'])

    Returns:
        The validated file path

    Raises:
        PathTraversalError: If the path attempts to escape the base directory
        FileNotFoundError: If must_exist is True and the file doesn't exist
        ValueError: If the file extension is not allowed
    """
    validated_path = validate_safe_path(path, base_dir)

    if must_exist and not validated_path.exists():
        raise FileNotFoundError(f"File not found: {validated_path}")

    if must_exist and not validated_path.is_file():
        raise ValueError(f"Path is not a file: {validated_path}")

    if extensions:
        # Normalize extensions to lowercase with leading dot
        normalized_extensions = {
            ext if ext.startswith(".") else f".{ext}"
            for ext in (e.lower() for e in extensions)
        }

        if validated_path.suffix.lower() not in normalized_extensions:
            raise ValueError(
                f"Invalid file extension '{validated_path.suffix}'. "
                f"Allowed: {', '.join(sorted(normalized_extensions))}"
            )

    return validated_path


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """Sanitize a filename by removing dangerous characters.

    Args:
        filename: The filename to sanitize
        replacement: Character to use for replacing dangerous characters

    Returns:
        Sanitized filename

    Examples:
        >>> sanitize_filename("../../etc/passwd")
        'etc_passwd'

        >>> sanitize_filename("file<script>.txt")
        'file_script.txt'
    """
    if not filename:
        raise ValueError("Filename cannot be empty")

    # Remove null bytes
    sanitized = filename.replace("\0", "")

    # Replace path separators and characters that are dangerous on common filesystems
    dangerous_chars = [
        "/",
        "\\",
        "<",
        ">",
        ":",
        '"',
        "|",
        "?",
        "*",
        "\n",
        "\r",
        "\t",
    ]
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, replacement)

    # Collapse repeated dots to a single separator to retain extensions while
    # neutralising traversal attempts like "..".
    sanitized = re.sub(r"\.+", ".", sanitized)
    sanitized = re.sub(rf"{re.escape(replacement)}+(\.)", r"\1", sanitized)
    sanitized = re.sub(rf"(\.){re.escape(replacement)}+", r"\1", sanitized)

    # Strip leading/trailing separators and dots that could create hidden files
    sanitized = sanitized.strip(f"{replacement} .")

    if not sanitized:
        sanitized = "unnamed_file"

    return sanitized


def ensure_directory_exists(
    path: Union[str, Path],
    base_dir: Union[str, Path],
    create_parents: bool = True,
) -> Path:
    """Safely ensure a directory exists within the base directory.

    Args:
        path: The directory path to create
        base_dir: The base directory that the path must be within
        create_parents: If True, create parent directories as needed

    Returns:
        The validated directory path

    Raises:
        PathTraversalError: If the path attempts to escape the base directory
    """
    validated_path = validate_safe_path(path, base_dir)

    if not validated_path.exists():
        validated_path.mkdir(parents=create_parents, exist_ok=True)
    elif not validated_path.is_dir():
        raise ValueError(f"Path exists but is not a directory: {validated_path}")

    return validated_path


__all__ = [
    "PathTraversalError",
    "validate_safe_path",
    "validate_file_path",
    "sanitize_filename",
    "ensure_directory_exists",
]
