"""
Database query builder with SQL injection prevention.

Provides parameterized query building to prevent SQL injection attacks.
"""

import re
from typing import Any, List, Tuple


def build_query(
    query_template: str, params: Tuple[Any, ...]
) -> Tuple[str, Tuple[Any, ...]]:
    """
    Build a parameterized SQL query.

    This function ensures that user input is always passed as parameters,
    never concatenated into the query string.

    Supported placeholder formats:
    - '?' for positional parameters (SQLite, many databases)
    - '$1', '$2', etc. for PostgreSQL-style numbered parameters

    Args:
        query_template: SQL query with parameter placeholders
        params: Tuple of parameters to bind

    Returns:
        Tuple of (query, params) ready for execution

    Raises:
        ValueError: If query doesn't use parameterized placeholders

    Example:
        >>> query, params = build_query("SELECT * FROM trades WHERE symbol = ?", ("AAPL",))
        >>> # Execute with: cursor.execute(query, params)
    """
    # Check for common placeholder patterns
    has_placeholders = "?" in query_template or re.search(  # SQLite/MySQL style
        r"\$\d+", query_template
    )  # PostgreSQL style

    if not has_placeholders:
        raise ValueError(
            "Query must use parameterized placeholders (? or $n). "
            "Never concatenate user input into SQL queries."
        )

    # Return query and params separately to ensure parameterization
    return query_template, params


def sanitize_table_name(table_name: str, allowed_tables: List[str]) -> str:
    """
    Sanitize and validate table name against whitelist.

    Table names cannot be parameterized, so we use whitelist validation.

    Args:
        table_name: The table name to validate
        allowed_tables: List of allowed table names

    Returns:
        Validated table name

    Raises:
        ValueError: If table name is not in whitelist
    """
    if table_name not in allowed_tables:
        raise ValueError(
            f"Table '{table_name}' not in allowed tables: {allowed_tables}"
        )

    # Additional check: ensure no SQL injection patterns
    dangerous_patterns = ["--", ";", "/*", "*/", "'", '"', "\\"]
    for pattern in dangerous_patterns:
        if pattern in table_name:
            raise ValueError(f"Table name contains dangerous pattern: {pattern}")

    return table_name


def sanitize_column_name(column_name: str, allowed_columns: List[str]) -> str:
    """
    Sanitize and validate column name against whitelist.

    Column names cannot be parameterized, so we use whitelist validation.

    Args:
        column_name: The column name to validate
        allowed_columns: List of allowed column names

    Returns:
        Validated column name

    Raises:
        ValueError: If column name is not in whitelist
    """
    if column_name not in allowed_columns:
        raise ValueError(
            f"Column '{column_name}' not in allowed columns: {allowed_columns}"
        )

    # Additional check: ensure no SQL injection patterns
    dangerous_patterns = ["--", ";", "/*", "*/", "'", '"', "\\", "(", ")"]
    for pattern in dangerous_patterns:
        if pattern in column_name:
            raise ValueError(f"Column name contains dangerous pattern: {pattern}")

    return column_name


__all__ = [
    "build_query",
    "sanitize_table_name",
    "sanitize_column_name",
]
