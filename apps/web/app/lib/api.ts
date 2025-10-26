import 'server-only'

export type OverallHealthStatus = 'ready' | 'degraded' | 'failed'
export type ComponentStatus = 'operational' | 'degraded' | 'failed'

export interface ComponentHealth {
  healthy: boolean
  status: ComponentStatus
  detail?: string | null
  metrics?: Record<string, unknown>
}

export interface HealthResponse {
  status: OverallHealthStatus
  timestamp: string
  components: Record<string, ComponentHealth>
}

export class ApiConfigError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiConfigError'
  }
}

export class ApiResponseError extends Error {
  public readonly status: number

  constructor(message: string, status: number, options?: { cause?: unknown }) {
    super(message, options?.cause ? { cause: options.cause } : undefined)
    this.name = 'ApiResponseError'
    this.status = status
  }
}

function normaliseBaseUrl(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) {
    throw new ApiConfigError('API base URL is empty')
  }
  const url = new URL(trimmed)
  url.pathname = url.pathname.replace(/\/$/, '')
  return url.toString().replace(/\/$/, '')
}

function resolveApiBaseUrl(): string | null {
  const candidates = [
    process.env.TRADEPULSE_API_BASE_URL,
    process.env.NEXT_PUBLIC_API_BASE_URL,
  ]
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return normaliseBaseUrl(candidate)
    }
  }
  return null
}

function buildUrl(path: string): string {
  const baseUrl = resolveApiBaseUrl()
  if (!baseUrl) {
    throw new ApiConfigError(
      'API base URL is not configured. Set TRADEPULSE_API_BASE_URL or NEXT_PUBLIC_API_BASE_URL.',
    )
  }
  const base = new URL(baseUrl)
  const url = new URL(path, base)
  return url.toString()
}

async function fetchJson<T>(path: string): Promise<T> {
  const url = buildUrl(path)
  let response: Response
  try {
    response = await fetch(url, {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
      },
    })
  } catch (error) {
    throw new ApiResponseError(`Failed to reach backend at ${url}`, 503, { cause: error })
  }

  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new ApiResponseError(
      `Backend responded with status ${response.status}: ${body || 'no body returned'}`,
      response.status,
    )
  }

  try {
    return (await response.json()) as T
  } catch (error) {
    throw new ApiResponseError('Unable to parse backend JSON response.', response.status, { cause: error })
  }
}

async function fetchText(path: string): Promise<string> {
  const url = buildUrl(path)
  let response: Response
  try {
    response = await fetch(url, {
      cache: 'no-store',
      headers: {
        Accept: 'text/plain, */*',
      },
    })
  } catch (error) {
    throw new ApiResponseError(`Failed to reach backend at ${url}`, 503, { cause: error })
  }

  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new ApiResponseError(
      `Backend responded with status ${response.status}: ${body || 'no body returned'}`,
      response.status,
    )
  }

  return response.text()
}

export async function fetchHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/health')
}

export async function fetchMetrics(): Promise<string> {
  return fetchText('/metrics')
}

function tryBuildRealtimeFromHttp(baseUrl: string): string | null {
  try {
    const url = new URL(baseUrl)
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${protocol}//${url.host}/ws/stream`
    }
  } catch {
    return null
  }
  return null
}

function resolveExplicitRealtimeUrl(): string | null {
  const candidates = [
    process.env.TRADEPULSE_WS_BASE_URL,
    process.env.NEXT_PUBLIC_WS_BASE_URL,
  ]
  for (const candidate of candidates) {
    if (!candidate) {
      continue
    }
    try {
      const url = new URL(candidate.trim())
      if (!url.protocol.startsWith('ws')) {
        continue
      }
      url.pathname = url.pathname || '/ws/stream'
      url.search = ''
      url.hash = ''
      return url.toString()
    } catch {
      continue
    }
  }
  return null
}

export function getRealtimeStreamUrl(): string | null {
  const explicit = resolveExplicitRealtimeUrl()
  if (explicit) {
    return explicit
  }
  const baseUrl = resolveApiBaseUrl()
  if (!baseUrl) {
    return null
  }
  return tryBuildRealtimeFromHttp(baseUrl)
}

export function getApiBaseUrl(): string | null {
  return resolveApiBaseUrl()
}
