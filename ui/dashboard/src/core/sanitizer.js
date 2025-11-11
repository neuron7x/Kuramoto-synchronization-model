const DANGEROUS_TAGS = [
  'script',
  'style',
  'iframe',
  'object',
  'embed',
  'link',
  'meta',
  'base',
  'form',
  'noscript',
  'template',
];

const DANGEROUS_ATTR_NAMES = ['srcdoc'];

const URL_ATTR_NAMES = ['href', 'src', 'xlink:href', 'formaction'];

const JAVASCRIPT_URL_PATTERN = /javascript\s*:/i;

/**
 * Strip HTML tags for fallback sanitisation where DOM APIs are unavailable.
 * @param {unknown} html
 * @returns {string}
 */
export function stripHtmlTags(html) {
  if (html == null) {
    return '';
  }
  let input = String(html);
  input = input.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '');
  input = input.replace(/<style[\s\S]*?>[\s\S]*?<\/style>/gi, '');
  input = input.replace(/<noscript[\s\S]*?>[\s\S]*?<\/noscript>/gi, '');
  input = input.replace(/<[^>]*>/g, '');
  return input.replace(JAVASCRIPT_URL_PATTERN, '');
}

function sanitiseAttributes(node) {
  const attributes = Array.from(node.attributes || []);
  for (const attribute of attributes) {
    const name = attribute.name.toLowerCase();
    const value = attribute.value || '';
    if (name.startsWith('on')) {
      node.removeAttribute(attribute.name);
      continue;
    }
    if (DANGEROUS_ATTR_NAMES.includes(name)) {
      node.removeAttribute(attribute.name);
      continue;
    }
    if (URL_ATTR_NAMES.includes(name) && JAVASCRIPT_URL_PATTERN.test(value)) {
      node.removeAttribute(attribute.name);
      continue;
    }
    if (value && JAVASCRIPT_URL_PATTERN.test(value)) {
      node.removeAttribute(attribute.name);
    }
  }
}

function purgeDangerousNodes(root) {
  const selector = DANGEROUS_TAGS.join(',');
  if (selector) {
    const nodes = root.querySelectorAll(selector);
    nodes.forEach((element) => {
      if (element?.parentNode) {
        element.parentNode.removeChild(element);
      }
    });
  }
  root.querySelectorAll('*').forEach((element) => {
    sanitiseAttributes(element);
  });
}

function createFragmentFromDocument(doc) {
  const fragment = document.createDocumentFragment();
  while (doc.body && doc.body.firstChild) {
    fragment.appendChild(doc.body.firstChild);
  }
  return fragment;
}

function buildSafeFragment(html) {
  if (typeof document === 'undefined' || typeof DOMParser !== 'function') {
    return null;
  }
  const parser = new DOMParser();
  const input = html == null ? '' : String(html);
  const parsed = parser.parseFromString(`<body>${input}</body>`, 'text/html');
  if (!parsed || !parsed.body) {
    return document.createDocumentFragment();
  }
  purgeDangerousNodes(parsed.body);
  return createFragmentFromDocument(parsed);
}

function clearElement(target) {
  if (typeof target.replaceChildren === 'function') {
    target.replaceChildren();
    return;
  }
  while (target.firstChild) {
    target.removeChild(target.firstChild);
  }
}

/**
 * Safely inject HTML into a DOM node by sanitising the markup first.
 * Falls back to text rendering when DOM APIs are unavailable.
 *
 * @param {Element & { replaceChildren?: Function, textContent?: string }} target
 * @param {unknown} html
 */
export function injectSafeHtml(target, html) {
  if (!target) {
    return;
  }
  const fragment = buildSafeFragment(html);
  if (fragment) {
    if (typeof target.replaceChildren === 'function') {
      target.replaceChildren(fragment);
      return;
    }
    if (typeof target.appendChild === 'function') {
      clearElement(target);
      target.appendChild(fragment);
      return;
    }
  }

  if ('textContent' in target) {
    target.textContent = stripHtmlTags(html);
  }
}

export default injectSafeHtml;
