import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const REFRESH_COOKIE_NAME = 'tp.refreshToken'

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

