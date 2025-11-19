# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Input validation and sanitization utilities for security.

WARNING: These utilities are for display/logging purposes only.
For database queries, ALWAYS use parameterized queries.
For HTML output in templates, use framework-provided escaping.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


def sanitize_for_display(input_value: str) -> str:
    """Sanitize input for display/logging purposes ONLY.
    
    WARNING: This function is NOT safe for SQL queries. 
    ALWAYS use parameterized queries for database operations.
    This function is only for sanitizing values for display in logs or error messages.
    
    Args:
        input_value: The input string to sanitize for display
        
    Returns:
        String with potentially dangerous characters escaped for safe display
    """
    # Escape single quotes for display
    sanitized = input_value.replace("'", "''")
    # Remove SQL comment markers for display
    sanitized = sanitized.replace("--", "")
    # Remove semicolons for display
    sanitized = sanitized.replace(";", "")
    return sanitized


def escape_html(input_value: str) -> str:
    """Escape HTML to prevent XSS attacks.
    
    Args:
        input_value: The input string to escape
        
    Returns:
        HTML-escaped string
    """
    return html.escape(input_value, quote=True)


def validate_integer(input_value: str) -> int:
    """Validate and convert string to integer.
    
    Args:
        input_value: The input string to validate
        
    Returns:
        Validated integer value
        
    Raises:
        ValueError: If input is not a valid integer
    """
    # Strip whitespace
    cleaned = input_value.strip()
    
    # Check if it's a valid integer (including negative)
    if not re.match(r'^-?\d+$', cleaned):
        raise ValueError(f"Invalid integer: {input_value}")
    
    return int(cleaned)


def validate_email(email: str) -> bool:
    """Validate email address format with basic pattern matching.
    
    Note: This performs basic validation only and is not fully RFC 5322 compliant.
    For production use, consider using a specialized email validation library
    like email-validator or validate_email.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email matches basic pattern, False otherwise
    """
    # Basic pattern - not RFC 5322 compliant but catches most obvious invalid formats
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    # Additional basic checks
    if len(email) > 254:  # Max email length per RFC 5321
        return False
    if email.count('@') != 1:  # Must have exactly one @
        return False
    
    return bool(re.match(email_pattern, email))


def sanitize_filename(filename: str, base_dir: Path | None = None) -> str:
    """Sanitize filename to prevent path traversal attacks.
    
    WARNING: This function provides basic sanitization but should be used
    in conjunction with proper path validation using pathlib.Path.resolve()
    to ensure the resulting path stays within the intended directory.
    
    Args:
        filename: The filename to sanitize
        base_dir: Optional base directory to validate against
        
    Returns:
        Sanitized filename with dangerous characters removed
        
    Raises:
        ValueError: If filename is empty or contains only invalid characters
    """
    if not filename or not filename.strip():
        raise ValueError("Filename cannot be empty")
    
    # Remove path separators (including Unicode variants)
    sanitized = filename.replace('/', '').replace('\\', '')
    sanitized = sanitized.replace('\u2044', '').replace('\u2215', '')  # Unicode slashes
    
    # Remove parent directory references (multiple dots too)
    sanitized = re.sub(r'\.\.+', '', sanitized)
    
    # Remove null bytes and other control characters
    sanitized = sanitized.replace('\x00', '')
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    
    if not sanitized:
        raise ValueError("Filename contains only invalid characters")
    
    # If base_dir provided, validate the resulting path stays within it
    if base_dir is not None:
        try:
            full_path = (base_dir / sanitized).resolve()
            if not str(full_path).startswith(str(base_dir.resolve())):
                raise ValueError("Path traversal attempt detected")
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid filename: {e}")
    
    return sanitized


def is_safe_file_extension(filename: str, allowed_extensions: list[str]) -> bool:
    """Check if file extension is in allowed list.
    
    Note: This checks only the final extension. Be aware of double extension attacks
    (e.g., file.jpg.exe). Consider validating all extensions or the full filename.
    
    Args:
        filename: The filename to check
        allowed_extensions: List of allowed extensions including the dot (e.g., ['.jpg', '.png'])
        
    Returns:
        True if extension is allowed, False otherwise
        
    Raises:
        ValueError: If allowed_extensions contains invalid entries
    """
    # Validate allowed_extensions list
    for ext in allowed_extensions:
        if not ext.startswith('.'):
            raise ValueError(f"Extensions must start with '.': {ext}")
    
    if not filename or '.' not in filename:
        return False
    
    # Get file extension (final extension only)
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    
    # Check for double extensions that might be dangerous
    # e.g., file.jpg.exe should be rejected even if .jpg is allowed
    parts = filename.lower().split('.')
    if len(parts) > 2:
        # Check if any dangerous extension exists before the final one
        dangerous_exts = ['.exe', '.bat', '.cmd', '.sh', '.ps1', '.vbs', '.jar', '.dll']
        for part in parts[1:-1]:  # Check all but filename and final extension
            if f'.{part}' in dangerous_exts:
                return False
    
    return ext in allowed_extensions
