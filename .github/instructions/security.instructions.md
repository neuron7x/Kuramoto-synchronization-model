# Security instructions
- Do not use `subprocess` with `shell=True`.
- Never hardcode secrets in code, tests, fixtures, or workflows.
- Validate all untrusted input and fail closed by default.
- Guard against unsafe deserialization, SSRF, path traversal, and command injection.
- Treat `.github/workflows/**` changes as high-risk and enforce strict review.
