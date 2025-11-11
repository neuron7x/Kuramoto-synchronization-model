import assert from 'assert';

import { stripHtmlTags } from '../src/core/sanitizer.js';

const maliciousMarkup = `
  <div>
    Safe content
    <script>alert('owned')</script>
    <img src="javascript:alert('xss')" />
    <span onclick="alert('boom')">Click me</span>
  </div>
`;

const stripped = stripHtmlTags(maliciousMarkup);

assert.ok(!stripped.includes('<script>'), 'stripHtmlTags should remove script tags');
assert.ok(!stripped.includes("alert('owned')"), 'stripHtmlTags should drop script contents');
assert.ok(!/javascript\s*:/i.test(stripped), 'stripHtmlTags should remove javascript: urls');
assert.ok(stripped.includes('Safe content'), 'stripHtmlTags should retain text content');
