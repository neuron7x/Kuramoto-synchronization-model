function buildConnectSources() {
  const sources = new Set(["'self'"])
  const candidates = [
    process.env.TRADEPULSE_API_BASE_URL,
    process.env.NEXT_PUBLIC_API_BASE_URL,
    process.env.TRADEPULSE_WS_BASE_URL,
    process.env.NEXT_PUBLIC_WS_BASE_URL,
  ]

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== 'string') {
      continue
    }
    try {
      const url = new URL(candidate)
      const origin = `${url.protocol}//${url.host}`
      if (/^(https?:|wss?:)/.test(url.protocol)) {
        sources.add(origin)
      }
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        const wsProtocol = url.protocol === 'https:' ? 'wss' : 'ws'
        sources.add(`${wsProtocol}://${url.host}`)
      }
    } catch {
      // Ignore malformed URLs so a typo does not break builds.
    }
  }

  return Array.from(sources)
}

const connectSrc = buildConnectSources().join(' ')

const ContentSecurityPolicy = [
  "default-src 'self';",
  "base-uri 'self';",
  "script-src 'self';",
  "style-src 'self' 'unsafe-inline';",
  "img-src 'self' data: blob:;",
  "font-src 'self';",
  `connect-src ${connectSrc};`,
  "frame-ancestors 'none';",
  "form-action 'self';",
  "object-src 'none';",
  "worker-src 'self';",
  "media-src 'self';",
  "manifest-src 'self';",
].join(' ')

const securityHeaders = [
  {
    key: 'Content-Security-Policy',
    value: ContentSecurityPolicy,
  },
  {
    key: 'Referrer-Policy',
    value: 'strict-origin-when-cross-origin',
  },
  {
    key: 'X-Frame-Options',
    value: 'DENY',
  },
  {
    key: 'X-Content-Type-Options',
    value: 'nosniff',
  },
  {
    key: 'X-DNS-Prefetch-Control',
    value: 'off',
  },
  {
    key: 'Strict-Transport-Security',
    value: 'max-age=63072000; includeSubDomains; preload',
  },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=()',
  },
  {
    key: 'Cross-Origin-Opener-Policy',
    value: 'same-origin',
  },
  {
    key: 'Cross-Origin-Resource-Policy',
    value: 'same-origin',
  },
  {
    key: 'Cross-Origin-Embedder-Policy',
    value: 'require-corp',
  },
]

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: securityHeaders,
      },
    ]
  },
}

module.exports = nextConfig
