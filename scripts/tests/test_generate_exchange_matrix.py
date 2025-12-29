from __future__ import annotations

import types
from pathlib import Path

import scripts.generate_exchange_matrix as gen


def test_main_writes_matrix(monkeypatch, tmp_path: Path) -> None:
    adapters = [
        (None, "execution.adapters.alpha", False),
        (None, "execution.adapters.beta", False),
    ]
    monkeypatch.setattr(gen.pkgutil, "walk_packages", lambda *a, **k: adapters)

    def fake_import(name: str):
        mod = types.SimpleNamespace()
        if name.endswith("alpha"):
            mod.get_server_time = lambda: None
            mod.get_exchange_info = lambda: None
            mod.get_balance = lambda: None
        else:
            mod.time = lambda: None
        return mod

    monkeypatch.setattr(gen.importlib, "import_module", fake_import)
    output = tmp_path / "out.md"

    monkeypatch.setattr(
        gen.argparse.ArgumentParser, "parse_args", lambda self: types.SimpleNamespace(write=output)
    )

    gen.main()

    content = output.read_text()
    assert "alpha" in content
    assert "beta" in content


def test_adapter_import_failure_skipped(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gen.pkgutil, "walk_packages", lambda *a, **k: [(None, "execution.adapters.missing", False)])
    def raise_import(_):
        raise ImportError()

    monkeypatch.setattr(gen.importlib, "import_module", raise_import)
    output = tmp_path / "out.md"
    monkeypatch.setattr(
        gen.argparse.ArgumentParser, "parse_args", lambda self: types.SimpleNamespace(write=output)
    )

    gen.main()
    assert "Exchange Compatibility Matrix" in output.read_text()
