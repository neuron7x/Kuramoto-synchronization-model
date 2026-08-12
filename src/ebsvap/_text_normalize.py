#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adversarial text normalization for the EBSVAP claim compiler.

The forbidden-strength-word guard in ``claim_compiler`` matches regexes against
claim text. Raw matching is trivially evaded by:

  * homoglyphs — Cyrillic/Greek letters that render identically to Latin
    ("prоven" with Cyrillic о U+043E reads as "proven" but does not match);
  * zero-width / format characters — U+200B ZWSP, U+200C/D ZWNJ/ZWJ, U+FEFF
    ("pro<ZWSP>ven" splits the token);
  * control characters incl. NUL ("pro\\x00ven").

``normalize_for_matching`` collapses all three evasion channels into a plain
ASCII-comparable form BEFORE matching, so the guard sees the canonical token.
It NEVER admits: its only effect is to expose a hidden strength word to the
existing fail-closed matcher. Benign ASCII text is returned unchanged (NFKC is
a no-op on already-canonical ASCII), so currently-passing inputs are preserved.
"""

from __future__ import annotations

import unicodedata

# Common Cyrillic / Greek confusables of Latin letters, folded to their ASCII
# twin. Both letter cases are listed so folding is independent of the caller's
# case handling. This is a deliberately conservative, well-known subset (the
# Unicode "confusables" homoglyph classes for Latin a e o p c x i s y k h m t b
# n v j l q w); over-folding a homoglyph can only expose a strength word to the
# fail-closed guard, never hide one.
# CANONICAL confusable table — MUST stay byte-identical to the copy in
# ``scripts/ci/_text_normalize.py`` (a test asserts equality). Case-preserving
# so the fold is independent of downstream case handling; both consumers match
# case-insensitively, so over/under-casing here is harmless. Keys are the
# confusable codepoints; values their ASCII twin.
_CONFUSABLES: dict[str, str] = {
    # --- Cyrillic (lowercase) -> Latin ---
    "а": "a",
    "е": "e",
    "ё": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "х": "x",
    "у": "y",
    "і": "i",
    "ѕ": "s",
    "ј": "j",
    "к": "k",
    "м": "m",
    "т": "t",
    "в": "b",
    "н": "h",
    "и": "n",
    "һ": "h",
    "ӏ": "l",
    "ԛ": "q",
    "ԝ": "w",
    # --- Cyrillic (uppercase) -> Latin ---
    "А": "A",
    "Е": "E",
    "Ё": "E",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Х": "X",
    "У": "Y",
    "І": "I",
    "Ѕ": "S",
    "Ј": "J",
    "К": "K",
    "М": "M",
    "Т": "T",
    "В": "B",
    "Н": "H",
    "И": "N",
    "Һ": "H",
    # --- Greek (lowercase) -> Latin ---
    "α": "a",
    "ο": "o",
    "ρ": "p",
    "ε": "e",
    "χ": "x",
    "ν": "v",
    "τ": "t",
    "ι": "i",
    "κ": "k",
    # --- Greek (uppercase) -> Latin ---
    "Α": "A",
    "Β": "B",
    "Ε": "E",
    "Η": "H",
    "Ι": "I",
    "Κ": "K",
    "Μ": "M",
    "Ν": "N",
    "Ο": "O",
    "Ρ": "P",
    "Τ": "T",
    "Χ": "X",
    "Ζ": "Z",
}

_CONFUSABLE_TABLE = str.maketrans(_CONFUSABLES)


def normalize_for_matching(s: str) -> str:
    """Return an ASCII-comparable form of ``s`` for forbidden-word matching.

    Pipeline (order matters):
      1. Strip Unicode ``Cc`` (control, incl. NUL) and ``Cf`` (format, incl.
         ZWSP U+200B, ZWNJ U+200C, ZWJ U+200D, BOM U+FEFF) — pure evasion
         channels with no lexical content.
      2. NFKD decompose — split base letters from combining accents AND fold
         compatibility variants (full-width, ligatures, mathematical alphanums)
         down to their base characters.
      3. Strip combining marks (``Mn``/``Mc``/``Me``) so a base letter carrying
         a combining diacritic (``o`` + U+0301 → ``ó``) cannot dodge the ASCII
         pattern.
      4. Fold known Cyrillic/Greek homoglyphs to their Latin ASCII twin.

    Non-string input raises ``TypeError`` — callers must type-guard first (the
    claim compiler does, fail-closed). Benign ASCII is returned unchanged.
    """
    if not isinstance(s, str):
        raise TypeError(f"normalize_for_matching expects str, got {type(s).__name__}")
    if not s:
        return s
    # 1. drop control (Cc) + format (Cf) invisibles, NUL included
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cc", "Cf"))
    # 2. compatibility DEcomposition — accents split off; full-width/ligatures/
    #    math-alphanumerics collapse to base ASCII
    s = unicodedata.normalize("NFKD", s)
    # 3. strip combining marks so o+U+0301 (ó) reduces to o
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Mn", "Mc", "Me"))
    # 4. fold homoglyphs to ASCII so the downstream regex sees the real token
    return s.translate(_CONFUSABLE_TABLE)
