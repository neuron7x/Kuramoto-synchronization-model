import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

const PUBLIC_FILE = /\.(.*)$/
const PUBLIC_ROUTES = ['/signin']
const REFRESH_COOKIE_NAME = 'tp.refreshToken'

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (PUBLIC_FILE.test(pathname) || pathname.startsWith('/api/auth')) {
    return NextResponse.next()
  }

  const hasSession = request.cookies.has(REFRESH_COOKIE_NAME)
  const isPublicRoute = PUBLIC_ROUTES.includes(pathname)

  if (!hasSession && !isPublicRoute) {
    const url = request.nextUrl.clone()
    url.pathname = '/signin'
    url.searchParams.set('redirect', pathname)
    return NextResponse.redirect(url)
  }

  if (hasSession && isPublicRoute) {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
