# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Input validation and sanitization utilities for security."""
from __future__ import annotations

import html
import re
from typing import Any


def sanitize_sql_input(input_value: str) -> str:
    """Sanitize input for SQL queries (basic escaping).
    
    Note: Always prefer parameterized queries over sanitization.
    
    Args:
        input_value: The input string to sanitize
        
    Returns:
        Sanitized string with dangerous characters escaped
    """
    # Escape single quotes for SQL
    sanitized = input_value.replace("'", "''")
    # Remove SQL comment markers
    sanitized = sanitized.replace("--", "")
    # Remove semicolons (statement terminators)
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
    """Validate email address format.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if valid, False otherwise
    """
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename with dangerous characters removed
    """
    # Remove path separators
    sanitized = filename.replace('/', '').replace('\\', '')
    # Remove parent directory references
    sanitized = sanitized.replace('..', '')
    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')
    return sanitized


def is_safe_file_extension(filename: str, allowed_extensions: list[str]) -> bool:
    """Check if file extension is in allowed list.
    
    Args:
        filename: The filename to check
        allowed_extensions: List of allowed extensions (e.g., ['.jpg', '.png'])
        
    Returns:
        True if extension is allowed, False otherwise
    """
    # Get file extension
    ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in allowed_extensions
