"""Pytest configuration for QLW tests.

This conftest isolates QLW tests from the main project dependencies.
"""

import sys
from pathlib import Path

# Ensure the src directory is in the path for imports
repo_root = Path(__file__).parent.parent.parent
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
