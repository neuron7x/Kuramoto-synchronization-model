import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

const REFRESH_COOKIE_NAME = 'gs.refreshToken'

export async function POST() {
  const cookieStore = await cookies()
  const refreshToken = cookieStore.get(REFRESH_COOKIE_NAME)

  if (!refreshToken || !refreshToken.value) {
    return NextResponse.json({ error: 'No active session' }, { status: 401 })
  }

  const accessToken = crypto.randomUUID()
  const expiresAt = Date.now() + 15 * 60 * 1000

  return NextResponse.json({ accessToken, expiresAt })
}
