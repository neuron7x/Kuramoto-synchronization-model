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
 */
function isSafeUrl(url) {
  if (!url || typeof url !== 'string') {
    return false;
  }
  
  // Block javascript: and data: URLs
  const trimmed = url.trim().toLowerCase();
  if (trimmed.startsWith('javascript:') || trimmed.startsWith('data:')) {
    return false;
  }
  
  // Check protocol if URL is absolute
  try {
    const parsed = new URL(url, 'http://localhost');
    return ALLOWED_PROTOCOLS.has(parsed.protocol);
  } catch {
    // Relative URL, consider safe
    return true;
  }
}

/**
 * Sanitize HTML with whitelist
 * Note: This is a basic implementation. For production, consider using DOMPurify
 */
export function sanitizeHtml(html, options = {}) {
  // Note: allowedTags and allowedAttributes will be used when full implementation is added
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { allowedTags = ALLOWED_TAGS, allowedAttributes = ALLOWED_ATTRIBUTES } = options;
  
  if (!html || typeof html !== 'string') {
    return '';
  }
  
  // For now, use a simple tag stripper
  // In production, this should be replaced with a proper HTML parser like DOMPurify
  let result = html;
  
  // Remove script tags and their content
  // eslint-disable-next-line security/detect-unsafe-regex -- Simplified pattern, to be replaced with DOMPurify
  result = result.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  
  // Remove style tags and their content
  // eslint-disable-next-line security/detect-unsafe-regex -- Simplified pattern, to be replaced with DOMPurify
  result = result.replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '');
  
  // Remove event handlers
  result = result.replace(/\s*on\w+\s*=\s*["'][^"']*["']/gi, '');
  result = result.replace(/\s*on\w+\s*=\s*[^\s>]*/gi, '');
  
  // Sanitize href attributes
  result = result.replace(/href\s*=\s*["']([^"']*)["']/gi, (match, url) => {
    return isSafeUrl(url) ? match : '';
  });
  
  return result;
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
