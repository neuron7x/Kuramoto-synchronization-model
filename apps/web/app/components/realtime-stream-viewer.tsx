'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

interface StreamEvent {
  id: number
  receivedAt: Date
  payload: string
  formatted: string
}

type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'closed' | 'error' | 'unsupported'

function parsePayload(raw: string): string {
  try {
    const parsed = JSON.parse(raw)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return raw
  }
}

export function RealtimeStreamViewer({ url }: { url: string | null }) {
  const [status, setStatus] = useState<ConnectionStatus>(url ? 'idle' : 'unsupported')
  const [events, setEvents] = useState<StreamEvent[]>([])
  const nextIdRef = useRef(0)

  const statusLabel = useMemo(() => {
    switch (status) {
      case 'connecting':
        return 'Connecting'
      case 'connected':
        return 'Connected'
      case 'closed':
        return 'Disconnected'
      case 'error':
        return 'Connection error'
      case 'unsupported':
        return 'Realtime stream unavailable'
      default:
        return 'Idle'
    }
  }, [status])

  useEffect(() => {
    if (!url) {
      setStatus('unsupported')
      return
    }
    if (typeof window === 'undefined' || typeof window.WebSocket === 'undefined') {
      setStatus('unsupported')
      return
    }

    setStatus('connecting')
    let mounted = true
    let socket: WebSocket | null = null

    try {
      socket = new WebSocket(url)
    } catch (error) {
      console.error('Failed to open websocket', error)
      setStatus('error')
      return
    }

    socket.addEventListener('open', () => {
      if (!mounted) {
        return
      }
      setStatus('connected')
    })

    socket.addEventListener('message', (event) => {
      if (!mounted) {
        return
      }
      setEvents((previous) => {
        nextIdRef.current += 1
        const next: StreamEvent = {
          id: nextIdRef.current,
          receivedAt: new Date(),
          payload: event.data,
          formatted: parsePayload(event.data),
        }
        const updated = [next, ...previous]
        return updated.slice(0, 20)
      })
    })

    socket.addEventListener('close', () => {
      if (!mounted) {
        return
      }
      setStatus('closed')
    })

    socket.addEventListener('error', () => {
      if (!mounted) {
        return
      }
      setStatus('error')
    })

    return () => {
      mounted = false
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        socket.close(1000, 'component disposed')
      }
    }
  }, [url])

  return (
    <div className="realtime-panel" data-testid="realtime-panel">
      <div className="realtime-status" data-testid="realtime-status">
        <span className={`status-dot status-dot--${status}`} aria-hidden="true" />
        <span>{statusLabel}</span>
        {url ? (
          <span className="realtime-url" data-testid="realtime-url">
            {url}
          </span>
        ) : null}
      </div>

      {status === 'unsupported' ? (
        <p className="tp-helper" role="note">
          Provide <code>TRADEPULSE_API_BASE_URL</code> or <code>TRADEPULSE_WS_BASE_URL</code> to enable realtime streaming from the
          backend analytics store.
        </p>
      ) : null}

      <div className="realtime-log" data-testid="realtime-log">
        {events.length === 0 ? (
          <p className="realtime-log__placeholder">Awaiting realtime updates…</p>
        ) : (
          events.map((event) => (
            <article key={event.id} className="realtime-log__entry">
              <header>
                <span>{event.receivedAt.toLocaleTimeString()}</span>
              </header>
              <pre>{event.formatted}</pre>
            </article>
          ))
        )}
      </div>
    </div>
  )
}
