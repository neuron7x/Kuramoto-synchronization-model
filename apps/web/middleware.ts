import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

const PUBLIC_FILE = /\.(.*)$/
const PUBLIC_ROUTES = ['/signin', '/api/health']
const REFRESH_COOKIE_NAME = 'tp.refreshToken'

// API proxy configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const PROXY_TIMEOUT = 30000

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Handle API proxy requests
  if (pathname.startsWith('/api/proxy/')) {
    return handleApiProxy(request)
  }

  // Skip middleware for public files and auth endpoints
  if (
    PUBLIC_FILE.test(pathname) ||
    pathname.startsWith('/api/auth') ||
    pathname.startsWith('/api/health')
  ) {
    return NextResponse.next()
  }

  const hasSession = request.cookies.has(REFRESH_COOKIE_NAME)
  const isPublicRoute = PUBLIC_ROUTES.includes(pathname)

  // Redirect to signin if not authenticated
  if (!hasSession && !isPublicRoute) {
    const url = request.nextUrl.clone()
    url.pathname = '/signin'
    url.searchParams.set('redirect', pathname)
    return NextResponse.redirect(url)
  }

  // Redirect to home if already authenticated and trying to access public route
  if (hasSession && isPublicRoute) {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

/**
 * Handle API proxy requests to the backend
 * This allows the frontend to call /api/proxy/* which will be forwarded to the backend
 */
async function handleApiProxy(request: NextRequest): Promise<NextResponse> {
  const { pathname, search } = request.nextUrl

  // Remove /api/proxy prefix and construct backend URL
  const backendPath = pathname.replace('/api/proxy', '')
  const backendUrl = `${API_BASE_URL}${backendPath}${search}`

  try {
    // Forward the request to the backend
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), PROXY_TIMEOUT)

    const headers = new Headers()

    // Copy relevant headers from the original request
    request.headers.forEach((value, key) => {
      if (!['host', 'connection', 'content-length'].includes(key.toLowerCase())) {
        headers.set(key, value)
      }
    })

    // Add X-Forwarded headers for tracing
    headers.set('X-Forwarded-For', request.ip || 'unknown')
    headers.set('X-Forwarded-Proto', request.nextUrl.protocol.replace(':', ''))
    headers.set('X-Forwarded-Host', request.nextUrl.host)

    const response = await fetch(backendUrl, {
      method: request.method,
      headers,
      body:
        request.method !== 'GET' && request.method !== 'HEAD' ? await request.text() : undefined,
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    // Create response with backend data
    const responseHeaders = new Headers(response.headers)

    // Add CORS headers if needed
    responseHeaders.set('Access-Control-Allow-Origin', request.headers.get('origin') || '*')
    responseHeaders.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    responseHeaders.set('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    responseHeaders.set('Access-Control-Allow-Credentials', 'true')

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    console.error('API Proxy error:', error)

    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json({ error: 'Request timeout' }, { status: 504 })
    }

    return NextResponse.json(
      { error: 'Proxy error', message: error instanceof Error ? error.message : 'Unknown error' },
      { status: 502 }
    )
  }
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
