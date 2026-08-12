import { timingSafeEqual } from 'node:crypto'
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const REFRESH_COOKIE_NAME = 'gs.refreshToken'
const CSRF_COOKIE_NAME = 'gs.csrfToken'
const CSRF_HEADER_NAME = 'x-geosync-csrf'

const invalidCsrf = () => NextResponse.json({ error: 'Invalid CSRF token' }, { status: 403 })

const validateCsrf = (request: NextRequest): NextResponse | null => {
  const headerToken = request.headers.get(CSRF_HEADER_NAME)
  const cookieToken = request.cookies.get(CSRF_COOKIE_NAME)?.value
  if (!headerToken || !cookieToken) {
    return NextResponse.json({ error: 'Missing CSRF token' }, { status: 403 })
  }

  const headerBytes = Buffer.from(headerToken, 'utf-8')
  const cookieBytes = Buffer.from(cookieToken, 'utf-8')

  if (headerBytes.length !== cookieBytes.length) {
    return invalidCsrf()
  }

  try {
    if (!timingSafeEqual(headerBytes, cookieBytes)) {
      return invalidCsrf()
    }
  } catch {
    return invalidCsrf()
  }

  return null
}

const isSecureCookieRequired = (request: NextRequest) => {
  if (process.env.NODE_ENV === 'production') {
    return true
  }

  const forwardedProto = request.headers.get('x-forwarded-proto')
  if (forwardedProto) {
    const primaryProto = forwardedProto.split(',')[0]?.trim().toLowerCase()
    if (primaryProto === 'https') {
      return true
    }
  }

  return request.nextUrl.protocol === 'https:'
}

export async function POST(request: NextRequest) {
  const csrfFailure = validateCsrf(request)
  if (csrfFailure) {
    return csrfFailure
  }
  const { refreshToken, expiresAt } = (await request.json()) as {
    refreshToken?: string
    expiresAt?: number
  }

  if (!refreshToken || typeof refreshToken !== 'string') {
    return NextResponse.json({ error: 'Missing refresh token' }, { status: 400 })
  }

  const expiryDate = typeof expiresAt === 'number' ? new Date(expiresAt) : undefined

  const response = NextResponse.json({ ok: true })
  response.cookies.set({
    name: REFRESH_COOKIE_NAME,
    value: refreshToken,
    httpOnly: true,
    sameSite: 'strict',
    secure: isSecureCookieRequired(request),
    path: '/',
    expires: expiryDate,
  })

  return response
}

export async function DELETE(request: NextRequest) {
  const csrfFailure = validateCsrf(request)
  if (csrfFailure) {
    return csrfFailure
  }
  const response = NextResponse.json({ ok: true })
  response.cookies.set({
    name: REFRESH_COOKIE_NAME,
    value: '',
    path: '/',
    httpOnly: true,
    sameSite: 'strict',
    secure: isSecureCookieRequired(request),
    expires: new Date(0),
  })
  return response
}
