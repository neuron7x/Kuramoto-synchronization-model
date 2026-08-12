#!/usr/bin/env node
// ⊛ neuron7xLab · CANON·2026 · i18n linter
//
// Three checks, any failure → exit 1:
//   A. Every leaf in strings has non-empty {uk, en} pair.
//   B. Every canon token listed in demo_strings.canonTokens that appears
//      in the "en" string must appear identically in the "uk" string
//      (and vice versa). Guarantees glyphs/brand/system ids stay invariant.
//   C. demo.html contains no stray user-facing hard-coded strings outside
//      an approved inline allowlist (canon + numeric only). Heuristic: any
//      text node ≥ 3 Cyrillic/Latin letters must come from a mustache/JS
//      render path, not a static literal in the HTML body between <main>
//      and its closing tag — EXCEPT strings inside <script>/<style> or
//      listed in INLINE_ALLOWLIST below.
//
// Run: `node ui/dashboard/scripts/validate_i18n.js`
// CI wrapper: .github/workflows/i18n.yml

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { dangerousLexemesIn, stripHtmlBlocks } from "./html_strip.js";

const __here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__here, "..");

const { strings, canonTokens } = await import(
  pathToFileURL(resolve(ROOT, "src/i18n/demo_strings.js")).href
);

const errors = [];

// ---------------- Check A · non-empty pairs ----------------
let totalKeys = 0;
for (const [ns, leafs] of Object.entries(strings)) {
  for (const [leaf, pair] of Object.entries(leafs)) {
    totalKeys += 1;
    if (!pair || typeof pair !== "object") {
      errors.push(`[A] ${ns}.${leaf}: not an object`);
      continue;
    }
    for (const loc of ["uk", "en"]) {
      if (typeof pair[loc] !== "string" || pair[loc].trim() === "") {
        errors.push(`[A] ${ns}.${leaf}.${loc}: empty or non-string`);
      }
    }
  }
}

// ---------------- Check B · canon invariance ----------------
// For tokens that are pure alnum (plus "-", "_", "*"), require a word-
// boundary match so "H" does not collide with "SHARPE" and "ok" does
// not collide with "Notebooks". Tokens containing any other character
// (glyphs like ⊛, subscripts like r_s with underscore, R² with ²) use
// plain substring — those are visually unambiguous anyway.
function canonMatcher(token) {
  if (/^[A-Za-z0-9_*+\-]+$/.test(token)) {
    // Escape regex metachars, then wrap with look-arounds that treat any
    // non-word (letter/digit/_) char as a boundary.
    const escaped = token.replace(/[-\\^$*+?.()|[\]{}]/g, "\\$&");
    const re = new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])`);
    return (s) => re.test(s);
  }
  return (s) => s.includes(token);
}
const canonMatchers = canonTokens.map((token) => ({
  token,
  has: canonMatcher(token),
}));

for (const [ns, leafs] of Object.entries(strings)) {
  for (const [leaf, pair] of Object.entries(leafs)) {
    if (!pair?.uk || !pair?.en) continue;
    for (const { token, has } of canonMatchers) {
      const inEn = has(pair.en);
      const inUk = has(pair.uk);
      if (inEn !== inUk) {
        errors.push(
          `[B] ${ns}.${leaf}: canon token "${token}" present in "${inEn ? "en" : "uk"}" but missing in "${inEn ? "uk" : "en"}"`,
        );
      }
    }
  }
}

// ---------------- Check C · demo.html literal scan ----------------
const demoPath = resolve(ROOT, "demo.html");
let demoRaw;
try {
  demoRaw = readFileSync(demoPath, "utf8");
} catch (e) {
  errors.push(`[C] could not read demo.html: ${e.message}`);
}

// Strip <script>, <style>, comments, AND every element carrying data-i18n /
// data-i18n-placeholder — the fallback text inside such elements is bound at
// page load and therefore not a hard-coded literal.
//
// Sanitizer + fail-closed barrier live in ./html_strip.js. See CodeQL alerts
// #702–#705 for the bypass vectors the previous inline regex missed.
const stripped = stripHtmlBlocks(demoRaw);
for (const lexeme of dangerousLexemesIn(stripped)) {
  errors.push(
    `[C] strip regex bypass: stripped HTML still contains "${lexeme}" — ` +
      `fix ui/dashboard/scripts/html_strip.js before proceeding.`,
  );
}

// Words on canon list OR inline-approved (numbers, symbols, units).
const allowlist = new Set([
  ...canonTokens,
  "UA", "EN", "menu", "меню", "ms", "bp", "USD", "UTC", "—",
  // numeric & punctuation — empty strings after regex split are OK
]);

// Extract text nodes between tags, ignoring quoted attributes.
const textNodeRe = />([^<]+)</g;
const hardLiterals = [];
let match;
while ((match = textNodeRe.exec(stripped)) !== null) {
  const raw = match[1].replace(/\s+/g, " ").trim();
  if (!raw) continue;
  // Tokenise by whitespace/punctuation that is NEVER meaningful prose.
  const tokens = raw.split(/[\s·|,;:()[\]{}<>&]+/).filter(Boolean);
  for (const tok of tokens) {
    if (tok.length < 2) continue;
    if (/^[+\-]?\d/.test(tok)) continue; // numeric
    if (/^[\p{P}\p{S}]+$/u.test(tok)) continue; // punctuation/symbol only
    if (allowlist.has(tok)) continue;
    // Any token with a Cyrillic or Latin letter is a user-facing literal.
    if (/[\p{L}]/u.test(tok)) {
      hardLiterals.push(tok);
    }
  }
}

const uniqueLiterals = Array.from(new Set(hardLiterals)).sort();
if (uniqueLiterals.length > 0) {
  errors.push(
    `[C] demo.html contains ${uniqueLiterals.length} hard-coded literals ` +
      `outside strings.js/canon allowlist:\n    ` +
      uniqueLiterals.slice(0, 40).join(", ") +
      (uniqueLiterals.length > 40 ? ` …(+${uniqueLiterals.length - 40} more)` : ""),
  );
}

// ---------------- report ----------------
if (errors.length === 0) {
  console.log(
    `⊛ i18n validator PASS · ${totalKeys} keys · ${canonTokens.length} canon tokens · demo.html clean`,
  );
  process.exit(0);
} else {
  console.error(`⊛ i18n validator FAIL · ${errors.length} issue(s):`);
  for (const e of errors) console.error("  " + e);
  process.exit(1);
}
