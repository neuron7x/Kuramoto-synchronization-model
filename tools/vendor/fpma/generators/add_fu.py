# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import json
from pathlib import Path

PY_MAIN = """# core entrypoint
def add(a:int,b:int)->int:
    return a+b
"""

PY_TEST = """from src.core import main

def test_add():
    assert main.add(2,3)==5
"""

PY_PORTS = """# abstract ports (interfaces)
class SumPort:
    def sum(self,a:int,b:int)->int: ...
"""

PY_ADAPTER = """# concrete adapter for SumPort
from src.ports.ports import SumPort

class LocalSum(SumPort):
    def sum(self,a:int,b:int)->int:
        return a+b
"""

NODE_PKG = """{
  "name": "%(name)s",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "test": "node tests/test.js"
  }
}
"""

NODE_CORE = """export function add(a, b){ return a + b }"""

NODE_TEST = """import { add } from '../src/core/index.js';
if (add(2,3)!==5) { throw new Error('bad') }"""

OPENAPI = """openapi: 3.1.0
info:
  title: %(name)s API
  version: 0.1.0
paths: {}
"""


def add_fu(
    root: Path,
    name: str,
    domain: str = "domains",
    lang: str = "python",
    with_openapi: bool = False,
):
    fu_root = root / domain / name
    if lang == "python":
        (fu_root / "src" / "core").mkdir(parents=True, exist_ok=True)
        (fu_root / "src" / "ports").mkdir(parents=True, exist_ok=True)
        (fu_root / "src" / "adapters").mkdir(parents=True, exist_ok=True)
        (fu_root / "tests").mkdir(parents=True, exist_ok=True)
        (fu_root / "config").mkdir(parents=True, exist_ok=True)
        (fu_root / "src" / "__init__.py").write_text("", encoding="utf-8")
        (fu_root / "src" / "core" / "__init__.py").write_text("", encoding="utf-8")
        (fu_root / "src" / "core" / "main.py").write_text(PY_MAIN, encoding="utf-8")
        (fu_root / "src" / "ports" / "__init__.py").write_text("", encoding="utf-8")
        (fu_root / "src" / "ports" / "ports.py").write_text(PY_PORTS, encoding="utf-8")
        (fu_root / "src" / "adapters" / "__init__.py").write_text("", encoding="utf-8")
        (fu_root / "src" / "adapters" / "local.py").write_text(PY_ADAPTER, encoding="utf-8")
        (fu_root / "tests" / "test_core.py").write_text(PY_TEST, encoding="utf-8")
        (fu_root / "config" / "README.md").write_text(
            "Use environment variables. See .env.example", encoding="utf-8"
        )
        (fu_root / ".env.example").write_text("EXAMPLE=1\n", encoding="utf-8")
    else:
        (fu_root / "src" / "core").mkdir(parents=True, exist_ok=True)
        (fu_root / "tests").mkdir(parents=True, exist_ok=True)
        (fu_root / "package.json").write_text(NODE_PKG % {"name": name}, encoding="utf-8")
        (fu_root / "src" / "core" / "index.js").write_text(NODE_CORE, encoding="utf-8")
        (fu_root / "tests" / "test.js").write_text(NODE_TEST, encoding="utf-8")
        (fu_root / ".env.example").write_text("EXAMPLE=1\n", encoding="utf-8")
    if with_openapi:
        (fu_root / "api").mkdir(parents=True, exist_ok=True)
        (fu_root / "api" / "openapi.yaml").write_text(OPENAPI % {"name": name}, encoding="utf-8")
    (fu_root / ".fpma.json").write_text(
        json.dumps({"language": lang, "name": name}, indent=2), encoding="utf-8"
    )
