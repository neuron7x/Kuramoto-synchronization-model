const ACCESS_TOKEN_STORAGE_KEY = 'gs.auth.access'
const ACCESS_TOKEN_KEY_STORAGE = 'gs.auth.crypto-key'

type PersistedAccessToken = {
  accessToken: string
  expiresAt: number
}

function decodeBase64(data: string): Uint8Array {
  const binary = globalThis.atob(data)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

function encodeBase64(data: Uint8Array): string {
  let binary = ''
  data.forEach((value) => {
    binary += String.fromCharCode(value)
  })
  return globalThis.btoa(binary)
}

function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer
}

async function resolveCryptoKey(): Promise<CryptoKey> {
  if (typeof window === 'undefined') {
    throw new Error('Token storage is not available on the server.')
  }

  const cryptoKey = sessionStorage.getItem(ACCESS_TOKEN_KEY_STORAGE)
  if (cryptoKey) {
    const raw = decodeBase64(cryptoKey)
    return crypto.subtle.importKey('raw', toArrayBuffer(raw), { name: 'AES-GCM' }, false, [
      'encrypt',
      'decrypt',
    ])
  }

  const rawKey = crypto.getRandomValues(new Uint8Array(32))
  const exportedKey = encodeBase64(rawKey)
  sessionStorage.setItem(ACCESS_TOKEN_KEY_STORAGE, exportedKey)
  return crypto.subtle.importKey('raw', toArrayBuffer(rawKey), { name: 'AES-GCM' }, false, [
    'encrypt',
    'decrypt',
  ])
}

export async function persistAccessToken(session: PersistedAccessToken): Promise<void> {
  if (typeof window === 'undefined') {
    return
  }

  try {
    const key = await resolveCryptoKey()
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const payload = new TextEncoder().encode(JSON.stringify(session))
    const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, payload)
    const storedValue = JSON.stringify({
      iv: encodeBase64(iv),
      data: encodeBase64(new Uint8Array(encrypted)),
    })
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, storedValue)
  } catch (error) {
    console.error('Failed to persist the encrypted access token.', error)
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  }
}

export async function readAccessToken(): Promise<PersistedAccessToken | null> {
  if (typeof window === 'undefined') {
    return null
  }

  const stored = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  if (!stored) {
    return null
  }

  try {
    const parsed = JSON.parse(stored) as { iv: string; data: string }
    if (!parsed?.iv || !parsed?.data) {
      throw new Error('Missing encryption metadata')
    }

    const key = await resolveCryptoKey()
    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: toArrayBuffer(decodeBase64(parsed.iv)) },
      key,
      toArrayBuffer(decodeBase64(parsed.data))
    )
    const payload = new TextDecoder().decode(decrypted)
    const session = JSON.parse(payload) as PersistedAccessToken

    if (!session?.accessToken || typeof session.expiresAt !== 'number') {
      throw new Error('Corrupted access token payload')
    }

    return session
  } catch (error) {
    console.error('Failed to load the encrypted access token.', error)
    localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
    return null
  }
}

export async function clearAccessToken(): Promise<void> {
  if (typeof window === 'undefined') {
    return
  }
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  sessionStorage.removeItem(ACCESS_TOKEN_KEY_STORAGE)
}
