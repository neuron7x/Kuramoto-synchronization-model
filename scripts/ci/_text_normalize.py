# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Confusable / invisible-character normalization for claim-firewall matching.

De-hype / terminology gates match ASCII forbidden-claim patterns against
free text. A naive ``re.search`` over raw text is trivially evaded by:

  * Unicode confusables -- a Latin letter swapped for a visually identical
    Cyrillic/Greek codepoint (``validаted`` with a Cyrillic ``а``);
  * zero-width / format characters spliced inside a word (``valid​ated``);
  * control characters, including NUL, used as separators (``valid\x00ated``).

``normalize_for_matching`` collapses all three so the ASCII pattern still
bites. It is deliberately conservative: it only folds a curated table of
well-known Latin look-alikes and strips Unicode categories ``Cc`` (control,
incl. NUL) and ``Cf`` (format, incl. ZWSP/ZWNJ/ZWJ/BOM). It never introduces
new word boundaries and never changes ASCII input.

NOTE: this module is intentionally independent of ``src/ebsvap/_text_normalize``
(a separate gate's compiler carries its own copy). The normalization contract
-- NFKC + confusable fold + Cc/Cf strip -- is shared; the code is not.
"""

from __future__ import annotations

import unicodedata

# Curated Latin look-alikes drawn from Cyrillic and Greek blocks. Keys are the
# confusable codepoints; values are their ASCII targets. Both letter cases are
# listed explicitly so downstream IGNORECASE matching still lines up.
# CANONICAL confusable table — MUST stay byte-identical to the copy in
# ``src/ebsvap/_text_normalize.py`` (a test asserts equality). Case-preserving;
# both consumers match case-insensitively so the fold case is harmless. Keys are
# the confusable codepoints; values their ASCII twin.
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
    """Return ``s`` folded so ASCII claim patterns match confusable/evasive text.

    Steps, in order:
      1. strip Unicode ``Cc`` (control incl. NUL) and ``Cf`` (format incl.
         ZWSP U+200B, ZWNJ, ZWJ, BOM U+FEFF) characters -- invisible splicers;
      2. NFKD-DEcompose -- split combining accents off base letters AND collapse
         compatibility forms (full-width, ligatures, mathematical alphanumerics);
      3. strip combining marks (``Mn``/``Mc``/``Me``) so a base letter carrying a
         combining diacritic (``o`` + U+0301 → ``ó``) cannot dodge the pattern;
      4. fold the curated Cyrillic/Greek confusable table to ASCII.

    Idempotent, and the identity on plain ASCII text.
    """
    if not s:
        return s
    # 1. Drop invisible splicers (control + format), NUL included.
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cc", "Cf"))
    # 2. Compatibility DEcomposition (accents split off; full-width/ligatures/
    #    math-alphanumerics collapse to base ASCII).
    s = unicodedata.normalize("NFKD", s)
    # 3. Strip combining marks so o+U+0301 (ó) reduces to o.
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Mn", "Mc", "Me"))
    # 4. Fold curated confusables to their ASCII look-alike.
    return s.translate(_CONFUSABLE_TABLE)
