// Copyright (c) 2026 Yaroslav Vasylenko (neuron7xLab)
// SPDX-License-Identifier: MIT
//
// Minimal HTML-strip helpers used by the i18n validator. Kept in a separate
// module so unit tests can exercise the sanitizer without running the full
// validator's top-level side effects (demo.html read, strings.js import).
//
// The strip regexes close CodeQL alerts #702–#705 (js/incomplete-multi-
// character-sanitization, js/bad-tag-filter) on
// ``ui/dashboard/scripts/validate_i18n.js``. The post-strip barrier
// ``dangerousLexemesIn`` is the explicit fail-closed check CodeQL recognises:
// if any dangerous lexeme survives the regex, the caller must treat the
// input as unsafe rather than scan the garbage.

/**
 * Strip <script>, <style>, HTML comments, and data-i18n[-placeholder]-bound
 * elements from a fragment of HTML.
 *
 * The regexes tolerate:
 *   * case-insensitive tag names (`i` flag)
 *   * attributes on the opening tag
 *   * whitespace-padded end tags ("</script >", "</style >") — HTML5-valid,
 *     which the previous patterns missed
 *   * `\b` prevents <scriptx>/<stylex> collisions
 *
 * @param {string} html Raw HTML (may be empty/null — treated as "").
 * @returns {string} Stripped HTML.
 */
export function stripHtmlBlocks(html) {
  return (html || "")
    .replace(/<script\b[\s\S]*?<\/script\s*>/gi, "")
    .replace(/<style\b[\s\S]*?<\/style\s*>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(
      /<([A-Za-z][A-Za-z0-9]*)[^>]*\sdata-i18n(?:-placeholder)?="[^"]*"[^>]*>[\s\S]*?<\/\1\s*>/g,
      "",
    );
}

/**
 * Return the list of dangerous lexemes still present in `stripped`.
 * Empty list = strip succeeded. Non-empty = regex bypass — callers must
 * treat the input as unsafe.
 *
 * This is the fail-closed barrier that CodeQL recognises as a complete
 * sanitizer for `js/incomplete-multi-character-sanitization`.
 *
 * @param {string} stripped Output of ``stripHtmlBlocks``.
 * @returns {string[]} Lexemes still present, in order of discovery.
 */
export function dangerousLexemesIn(stripped) {
  const lowered = stripped.toLowerCase();
  const found = [];
  for (const lexeme of ["<script", "<style", "<!--"]) {
    if (lowered.includes(lexeme)) found.push(lexeme);
  }
  return found;
}
