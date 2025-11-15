#!/usr/bin/env python3
"""Fix trailing whitespace in documentation files.

This script removes trailing whitespace from text files in the docs directory,
while preserving intentional double-space line breaks in Markdown.
"""
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

from __future__ import annotations

import sys
from pathlib import Path


def fix_trailing_whitespace(root: Path) -> int:
    """Fix trailing whitespace in files under the given root.

    Args:
        root: Root directory to process

    Returns:
        Number of files changed
    """
    if not root.exists():
        print(f"Error: {root} not found", file=sys.stderr)
        return -1

    # Extensions to process
    text_extensions = {
        ".md",
        ".rst",
        ".txt",
        ".yaml",
        ".yml",
        ".json",
        ".py",
        ".mdown",
        ".markdown",
    }

    changed = 0
    processed = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        # Process all text files
        if path.suffix.lower() not in text_extensions:
            continue

        try:
            text = path.read_bytes()
            original = text.decode("utf-8")
        except (UnicodeDecodeError, Exception) as e:
            print(f"Warning: Skipping {path}: {e}", file=sys.stderr)
            continue

        processed += 1

        # Process line by line, preserving double-space line breaks for Markdown
        lines = original.splitlines(keepends=True)
        fixed_lines = []

        for line in lines:
            # Remove newline for processing
            if line.endswith("\n"):
                content = line[:-1]
                ending = "\n"
            else:
                content = line
                ending = ""

            # Remove trailing spaces and tabs
            trimmed = content.rstrip(" \t")

            # Preserve Markdown hard line breaks (exactly two spaces)
            if content.endswith("  ") and not content.endswith("   "):
                # Keep the two-space line break
                fixed_lines.append(content + ending)
            else:
                # Remove all trailing whitespace
                fixed_lines.append(trimmed + ending)

        new_content = "".join(fixed_lines)

        # Preserve final newline if it existed
        if original and not original.endswith("\n") and new_content.endswith("\n"):
            new_content = new_content[:-1]

        if new_content != original:
            path.write_text(new_content, encoding="utf-8")
            changed += 1
            print(f"Fixed: {path.relative_to(root.parent)}")

    print(f"\nProcessed {processed} files, changed {changed} files")
    return changed


def main() -> int:
    """Main entry point."""
    root = Path("docs")
    result = fix_trailing_whitespace(root)
    return 0 if result >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
