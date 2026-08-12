from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "emit_pyo3_env.py"
spec = importlib.util.spec_from_file_location("emit_pyo3_env", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class EmitPyo3EnvSmokeTests(unittest.TestCase):
    def test_candidate_library_name_resolution(self) -> None:
        self.assertEqual(module._candidate_library_names("libpython3.13.so.1.0")[0], "python3.13")

    def test_resolve_env_returns_single_line_values(self) -> None:
        env = module.resolve_env()
        for line in env.lines():
            self.assertNotIn("\n", line)
            self.assertIn("=", line)


if __name__ == "__main__":
    unittest.main()
