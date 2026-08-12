#!/usr/bin/env node

/**
 * Audit the Next.js app for remote <script> inclusions.
 * Fails the process when http(s) script sources are detected so that
 * CSP hardening remains effective and no unreviewed third-party scripts
 * slip into production builds.
 */

const fs = require('fs')
const path = require('path')

const appDir = path.resolve(__dirname, '..', 'app')

/** @type {{ file: string; snippet: string; src: string }[]} */
const findings = []

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) {
      continue
    }
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(fullPath)
    } else if (/\.(tsx?|jsx?)$/.test(entry.name)) {
      inspectFile(fullPath)
    }
  }
}

function inspectFile(filePath) {
  const contents = fs.readFileSync(filePath, 'utf8')
  const relativePath = path.relative(path.resolve(__dirname, '..'), filePath)

  const scriptTagPattern = /<script[^>]+src=["'`](https?:\/\/[^"'`]+)["'`][^>]*>/gi
  const nextScriptPattern = /<Script[^>]+src={(?:["'`]?)(https?:\/\/[^"'`]+)(?:["'`]?)}[^>]*>/gi

  let match
  while ((match = scriptTagPattern.exec(contents)) !== null) {
    findings.push({
      file: relativePath,
      src: match[1],
      snippet: contents
        .slice(Math.max(match.index - 40, 0), Math.min(match.index + 120, contents.length))
        .trim(),
    })
  }
  while ((match = nextScriptPattern.exec(contents)) !== null) {
    findings.push({
      file: relativePath,
      src: match[1],
      snippet: contents
        .slice(Math.max(match.index - 40, 0), Math.min(match.index + 120, contents.length))
        .trim(),
    })
  }
}

walk(appDir)

if (findings.length > 0) {
  console.error('External script references detected:')
  for (const finding of findings) {
    console.error(`- ${finding.file}: ${finding.src}`)
    console.error(`  Context: ${finding.snippet}`)
  }
  console.error('\nReview and remove the remote script usage or explicitly document the exception.')
  process.exit(1)
}

console.log('External script audit passed: no remote script sources found.')
