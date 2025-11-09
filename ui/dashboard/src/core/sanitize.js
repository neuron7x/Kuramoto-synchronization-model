/**
 * Centralized HTML sanitization with whitelist support
 */

// Whitelist of allowed HTML tags
const ALLOWED_TAGS = new Set([
  'b', 'i', 'em', 'strong', 'u', 'span', 'div', 'p', 
  'br', 'a', 'ul', 'ol', 'li', 'code', 'pre'
]);

// Whitelist of allowed attributes per tag
const ALLOWED_ATTRIBUTES = {
  'a': ['href', 'title', 'target', 'rel'],
  'span': ['class'],
  'div': ['class'],
  'p': ['class'],
};

// URL protocol whitelist
const ALLOWED_PROTOCOLS = new Set(['http:', 'https:', 'mailto:']);

/**
 * Escape HTML entities
 */
export function escapeHtml(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).replace(/[&<>"']/g, (char) => {
    switch (char) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case "'":
        return '&#39;';
      default:
        return char;
    }
  });
}

/**
 * Check if a URL is safe
 * Prevents XSS attacks through malicious URLs
 */
function isSafeUrl(url) {
  if (!url || typeof url !== 'string') {
    return false;
  }
  
  // Normalize and check for dangerous protocols
  const trimmed = url.trim().toLowerCase();
  
  // Block dangerous pseudo-protocols that can execute scripts
  const dangerousProtocols = [
    'javascript:',
    'data:',
    'vbscript:',
    'file:',
    'about:',
  ];
  
  for (const protocol of dangerousProtocols) {
    if (trimmed.startsWith(protocol)) {
      return false;
    }
  }
  
  // Additional check for URL-encoded variations
  if (trimmed.includes('%6a%61%76%61%73%63%72%69%70%74') || // javascript
      trimmed.includes('%64%61%74%61')) { // data
    return false;
  }
  
  // Check protocol if URL is absolute
  try {
    const parsed = new URL(url, 'http://localhost');
    return ALLOWED_PROTOCOLS.has(parsed.protocol);
  } catch {
    // If URL parsing fails but it looks like a relative path, allow it
    // Reject anything that looks like it might be trying to bypass checks
    if (trimmed.includes(':')) {
      return false;
    }
    return true;
  }
}

/**
 * Sanitize HTML with whitelist
 * Note: This is a basic implementation. For production, consider using DOMPurify
 * 
 * SECURITY NOTE: This implementation uses simple regex-based sanitization which
 * is NOT as robust as a proper HTML parser. It's provided as a starting point
 * but should be replaced with DOMPurify or similar library for production use.
 */
export function sanitizeHtml(html, options = {}) {
  // Note: allowedTags and allowedAttributes will be used when full implementation is added
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { allowedTags = ALLOWED_TAGS, allowedAttributes = ALLOWED_ATTRIBUTES } = options;
  
  if (!html || typeof html !== 'string') {
    return '';
  }
  
  // For security, we use stripHtml for now which is simpler and safer
  // In production, this should be replaced with a proper HTML parser like DOMPurify
  // that properly parses the DOM tree and applies whitelist-based sanitization
  
  // For now, just escape all HTML to prevent XSS
  return escapeHtml(html);
}

/**
 * Strip all HTML tags
 */
export function stripHtml(html) {
  if (!html || typeof html !== 'string') {
    return '';
  }
  return html.replace(/<[^>]*>/g, '');
}

/**
 * Sanitize URL to prevent XSS
 */
export function sanitizeUrl(url) {
  if (!isSafeUrl(url)) {
    return '#';
  }
  return url;
}
