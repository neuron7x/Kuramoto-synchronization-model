// Copyright (c) 2026 Yaroslav Vasylenko (neuron7xLab)
// SPDX-License-Identifier: MIT
//
// Regression tests for ui/dashboard/scripts/html_strip.js. Closes CodeQL
// alerts #702–#705 (js/incomplete-multi-character-sanitization,
// js/bad-tag-filter) on ui/dashboard/scripts/validate_i18n.js.
//
// Uses node:test (built-in, no dependency). Run: `node --test tests/html_strip.test.js`.

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { dangerousLexemesIn, stripHtmlBlocks } from "../scripts/html_strip.js";

describe("stripHtmlBlocks — script tag variants", () => {
  const variants = [
    { html: "<script>alert(1)</script>", label: "plain" },
    { html: "<script >alert(1)</script >", label: "padded start + end" },
    { html: "<script\n>alert(1)</script\n>", label: "newline-padded tags" },
    { html: "<script\ttype=module>alert(1)</script\t>", label: "tab-separated" },
    { html: '<script type="module">alert(1)</script>', label: "attrs on opener" },
    { html: "<SCRIPT>alert(1)</SCRIPT>", label: "uppercase" },
    { html: "<ScRiPt>alert(1)</sCrIpT>", label: "mixed case" },
    { html: "<script>a</script><script>b</script>", label: "two scripts" },
    { html: "before<script>x</script>after", label: "surrounded by text" },
  ];
  for (const { html, label } of variants) {
    it(`removes <script> (${label})`, () => {
      const stripped = stripHtmlBlocks(html);
      assert.equal(dangerousLexemesIn(stripped).length, 0, `bypass: ${stripped}`);
      assert.equal(/script/i.test(stripped), false);
    });
  }
});

describe("stripHtmlBlocks — style tag variants", () => {
  const variants = [
    "<style>body{color:red}</style>",
    "<style >body{}</style >",
    '<style type="text/css">body{}</style>',
    "<STYLE>body{}</STYLE>",
    "<style\nmedia=screen>body{}</style\n>",
  ];
  for (const html of variants) {
    it(`removes <style> in ${JSON.stringify(html).slice(0, 40)}…`, () => {
      const stripped = stripHtmlBlocks(html);
      assert.equal(dangerousLexemesIn(stripped).length, 0);
      assert.equal(/style/i.test(stripped), false);
    });
  }
});

describe("stripHtmlBlocks — HTML comments", () => {
  const variants = [
    "<!-- normal -->",
    "<!-- multi\nline\ncomment -->",
    "before<!-- c -->middle<!-- d -->after",
    "<!---->",
    "<!-- contains <script> inside -->",
  ];
  for (const html of variants) {
    it(`removes comment in ${JSON.stringify(html).slice(0, 40)}…`, () => {
      const stripped = stripHtmlBlocks(html);
      assert.equal(dangerousLexemesIn(stripped).length, 0);
    });
  }
});

describe("stripHtmlBlocks — data-i18n bound elements", () => {
  it('removes <span data-i18n="x">...</span>', () => {
    const html = '<span data-i18n="foo.bar">fallback text</span>';
    assert.equal(stripHtmlBlocks(html), "");
  });
  it('removes <label data-i18n-placeholder="x">...</label>', () => {
    const html = '<label data-i18n-placeholder="placeholder">fallback</label>';
    assert.equal(stripHtmlBlocks(html), "");
  });
  it("preserves elements WITHOUT data-i18n", () => {
    const html = "<span>visible text</span>";
    assert.equal(stripHtmlBlocks(html), html);
  });
});

describe("dangerousLexemesIn — barrier detection", () => {
  it("empty on clean stripped output", () => {
    assert.deepEqual(dangerousLexemesIn("<p>hello</p>"), []);
  });
  it("detects leftover <script (case-insensitive)", () => {
    assert.deepEqual(dangerousLexemesIn("<Script ooops"), ["<script"]);
  });
  it("detects leftover <style", () => {
    assert.deepEqual(dangerousLexemesIn("<STYLE"), ["<style"]);
  });
  it("detects leftover <!--", () => {
    assert.deepEqual(dangerousLexemesIn("text <!-- unclosed"), ["<!--"]);
  });
  it("returns all three when all three leaked", () => {
    const leak = "<script <style <!-- here";
    assert.deepEqual(
      new Set(dangerousLexemesIn(leak)),
      new Set(["<script", "<style", "<!--"]),
    );
  });
});

describe("stripHtmlBlocks — prefix-collision guard (\\b anchor)", () => {
  it("does NOT strip tags whose name only starts with 'script'", () => {
    // <scriptx> is not a real script tag. The \b anchor prevents a false match.
    const html = "<scriptx>keep me</scriptx>";
    assert.equal(stripHtmlBlocks(html), html);
  });
  it("does NOT strip tags whose name only starts with 'style'", () => {
    const html = "<stylex>keep me</stylex>";
    assert.equal(stripHtmlBlocks(html), html);
  });
});

describe("stripHtmlBlocks — empty / null / absurd input", () => {
  it("handles empty string", () => {
    assert.equal(stripHtmlBlocks(""), "");
  });
  it("handles null / undefined as empty", () => {
    assert.equal(stripHtmlBlocks(null), "");
    assert.equal(stripHtmlBlocks(undefined), "");
  });
  it("leaves pure text untouched", () => {
    assert.equal(stripHtmlBlocks("hello world"), "hello world");
  });
});

describe("stripHtmlBlocks — barrier catches pathological interleaving", () => {
  // Regex-based stripping cannot possibly handle every interleaving of
  // comments containing fake script tags etc. — that's why the barrier
  // exists. Two complementary tests:
  //   1. Clean per-vector inputs: strip is complete, barrier finds nothing.
  //   2. Pathological interleaved input: strip may leave a comment fragment
  //      (a <script> inside a real <!-- … --> comment causes the script
  //      regex to eat across the comment), and the barrier MUST catch it.
  it("stripping is complete on clean inputs (barrier empty)", () => {
    const clean = [
      "<script >pwn()</script >",
      "<style\n>body{}</style\n>",
      "<!-- just a comment -->",
      "<SCRIPT>alert(1)</SCRIPT><style>x</style>",
      '<script type="module" src="x.js"></script>',
    ].join("\n");
    assert.deepEqual(dangerousLexemesIn(stripHtmlBlocks(clean)), []);
  });
  it("barrier detects leak when an unterminated <script> is inside a comment", () => {
    // The non-greedy script regex, faced with a <script> that has no </script>
    // inside the comment, extends beyond the comment to the next </script> on
    // a later line, leaving the "<!-- bypass " fragment dangling. This is a
    // known limitation of any regex-based HTML strip — the barrier MUST
    // surface it rather than silently emit garbage.
    const pathological =
      "<!-- bypass <script> -->intermediate\n" +
      "<SCRIPT>alert(1)</SCRIPT>";
    const stripped = stripHtmlBlocks(pathological);
    assert.ok(
      dangerousLexemesIn(stripped).length > 0,
      "barrier must fire on pathological interleaving; stripped=" +
        JSON.stringify(stripped),
    );
  });
});
