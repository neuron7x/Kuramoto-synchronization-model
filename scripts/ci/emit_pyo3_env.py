#!/usr/bin/env python3
"""Emit deterministic PyO3 linker environment for Rust tests.

The script runs under the exact Python interpreter selected for PyO3. It resolves
that interpreter's libpython path from sysconfig, verifies the shared library is
present, and writes the values consumed by Cargo to GitHub's environment file.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Pyo3Env:
    pyo3_python: str
    rustflags: str
    ld_library_path: str

    def lines(self) -> tuple[str, ...]:
        return (
            f"PYO3_PYTHON={single_line_env_value('PYO3_PYTHON', self.pyo3_python)}",
            f"RUSTFLAGS={single_line_env_value('RUSTFLAGS', self.rustflags)}",
            f"LD_LIBRARY_PATH={single_line_env_value('LD_LIBRARY_PATH', self.ld_library_path)}",
        )

    def shell_exports(self) -> str:
        return "\n".join(
            f"export {name}={shlex.quote(value)}"
            for name, value in (line.split("=", 1) for line in self.lines())
        )


def single_line_env_value(name: str, value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be a single-line environment value")
    return value


def _candidate_library_names(ldlibrary: str) -> tuple[str, ...]:
    if not ldlibrary.startswith("lib"):
        raise ValueError(f"LDLIBRARY must start with 'lib', got {ldlibrary!r}")
    stem = ldlibrary[3:]
    stripped = stem.split(".so", 1)[0].split(".dylib", 1)[0]
    return tuple(dict.fromkeys(part for part in (stripped, stem) if part))


def resolve_env(
    existing_ld_library_path: str = "",
    existing_rustflags: str = "",
) -> Pyo3Env:
    libdir = sysconfig.get_config_var("LIBDIR")
    ldlibrary = sysconfig.get_config_var("LDLIBRARY")
    if not libdir or not ldlibrary:
        raise RuntimeError(
            f"Cannot resolve libpython from LIBDIR={libdir!r}, LDLIBRARY={ldlibrary!r}"
        )

    libdir_path = Path(libdir)
    library_path = libdir_path / ldlibrary
    if not library_path.exists():
        raise RuntimeError(f"Resolved libpython does not exist: {library_path}")

    libname = _candidate_library_names(ldlibrary)[0]
    pyo3_rustflags = f"-L native={libdir_path} -l {libname}"
    rustflags = f"{existing_rustflags} {pyo3_rustflags}" if existing_rustflags else pyo3_rustflags
    ld_library_path = (
        f"{libdir_path}:{existing_ld_library_path}"
        if existing_ld_library_path
        else str(libdir_path)
    )
    return Pyo3Env(
        pyo3_python=sys.executable,
        rustflags=rustflags,
        ld_library_path=ld_library_path,
    )


def write_github_env(env: Pyo3Env, env_path: Path) -> None:
    with env_path.open("a", encoding="utf-8") as handle:
        for line in env.lines():
            handle.write(f"{line}\n")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print shell export commands instead of writing GITHUB_ENV",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        env = resolve_env(
            os.environ.get("LD_LIBRARY_PATH", ""),
            os.environ.get("RUSTFLAGS", ""),
        )
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.print:
        print(env.shell_exports())
        return 0

    github_env = os.environ.get("GITHUB_ENV")
    if not github_env:
        print(
            "ERROR: GITHUB_ENV is not set; use --print for local shells",
            file=sys.stderr,
        )
        return 1
    write_github_env(env, Path(github_env))
    print(f"PyO3 linker environment resolved for {env.pyo3_python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
