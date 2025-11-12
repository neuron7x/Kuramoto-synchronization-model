import { wsConfig } from '@/config/env'
import { logger } from '@/lib/utils/logger'

export enum ConnectionStatus {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
}

export interface WebSocketMessage<T = unknown> {
  type: string
  data: T
  timestamp: string
}

type MessageHandler<T = unknown> = (message: WebSocketMessage<T>) => void
type StatusHandler = (status: ConnectionStatus) => void
type ErrorHandler = (error: Error) => void

/**
 * WebSocket client with automatic reconnection and exponential backoff
 */
export class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private reconnectAttempts = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private status: ConnectionStatus = ConnectionStatus.DISCONNECTED
  private messageHandlers: Map<string, Set<MessageHandler>> = new Map()
  private statusHandlers: Set<StatusHandler> = new Set()
  private errorHandlers: Set<ErrorHandler> = new Set()
  private heartbeatInterval: NodeJS.Timeout | null = null
  private heartbeatTimeout: NodeJS.Timeout | null = null

  constructor(url: string = wsConfig.url) {
    this.url = url
  }

  /**
   * Connect to the WebSocket server
   */
  connect(): void {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
    ) {
      logger.warn('WebSocket already connected or connecting')
      return
    }

    this.setStatus(ConnectionStatus.CONNECTING)
    logger.info('Connecting to WebSocket', { url: this.url })

    try {
      this.ws = new WebSocket(this.url)
      this.setupEventHandlers()
    } catch (error) {
      logger.error('Failed to create WebSocket connection', error)
      this.handleError(error instanceof Error ? error : new Error('Connection failed'))
      this.scheduleReconnect()
    }
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect(): void {
    logger.info('Disconnecting from WebSocket')
    this.clearReconnectTimer()
    this.clearHeartbeat()

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
      this.ws = null
    }

    this.setStatus(ConnectionStatus.DISCONNECTED)
  }

  /**
   * Send a message to the server
   */
  send<T = unknown>(type: string, data: T): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      logger.error('Cannot send message: WebSocket not connected')
      throw new Error('WebSocket not connected')
    }

    const message: WebSocketMessage<T> = {
      type,
      data,
      timestamp: new Date().toISOString(),
    }

    this.ws.send(JSON.stringify(message))
    logger.debug('WebSocket message sent', { type })
  }

  /**
   * Subscribe to messages of a specific type
   */
  subscribe<T = unknown>(type: string, handler: MessageHandler<T>): () => void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, new Set())
    }

    this.messageHandlers.get(type)!.add(handler as MessageHandler)

    // Return unsubscribe function
    return () => {
      const handlers = this.messageHandlers.get(type)
      if (handlers) {
        handlers.delete(handler as MessageHandler)
        if (handlers.size === 0) {
          this.messageHandlers.delete(type)
        }
      }
    }
  }

  /**
   * Subscribe to connection status changes
   */
  onStatusChange(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler)
    // Immediately call with current status
    handler(this.status)

    return () => {
      this.statusHandlers.delete(handler)
    }
  }

  /**
   * Subscribe to errors
   */
  onError(handler: ErrorHandler): () => void {
    this.errorHandlers.add(handler)

    return () => {
      this.errorHandlers.delete(handler)
    }
  }

  /**
   * Get current connection status
   */
  getStatus(): ConnectionStatus {
    return this.status
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.status === ConnectionStatus.CONNECTED
  }

  private setupEventHandlers(): void {
    if (!this.ws) return

    this.ws.onopen = () => {
      logger.info('WebSocket connected')
      this.reconnectAttempts = 0
      this.setStatus(ConnectionStatus.CONNECTED)
      this.startHeartbeat()
    }

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WebSocketMessage
        this.handleMessage(message)
        this.resetHeartbeat()
      } catch (error) {
        logger.error('Failed to parse WebSocket message', error, { data: event.data })
      }
    }

    this.ws.onerror = (event) => {
      logger.error('WebSocket error', new Error('WebSocket error'), { event })
      this.handleError(new Error('WebSocket error'))
    }

    this.ws.onclose = (event) => {
      logger.info('WebSocket closed', { code: event.code, reason: event.reason })
      this.clearHeartbeat()

      if (event.code !== 1000) {
        // Not a normal closure, schedule reconnect
        this.scheduleReconnect()
      } else {
        this.setStatus(ConnectionStatus.DISCONNECTED)
      }
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    // Handle heartbeat/pong messages
    if (message.type === 'pong' || message.type === 'heartbeat') {
      return
    }

    const handlers = this.messageHandlers.get(message.type)
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(message)
        } catch (error) {
          logger.error(`Error in message handler for type: ${message.type}`, error)
        }
      })
    }
  }

  private handleError(error: Error): void {
    this.setStatus(ConnectionStatus.ERROR)
    this.errorHandlers.forEach((handler) => {
      try {
        handler(error)
      } catch (err) {
        logger.error('Error in error handler', err)
      }
    })
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= wsConfig.maxReconnectAttempts) {
      logger.error('Max reconnect attempts reached')
      this.setStatus(ConnectionStatus.DISCONNECTED)
      return
    }

    this.setStatus(ConnectionStatus.RECONNECTING)

    const delay = this.calculateReconnectDelay()
    logger.info(
      `Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1}/${wsConfig.maxReconnectAttempts})`
    )

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++
      this.connect()
    }, delay)
  }

  private calculateReconnectDelay(): number {
    const baseDelay = wsConfig.reconnectDelay
    const maxDelay = wsConfig.maxReconnectDelay
    const backoff = wsConfig.reconnectBackoff

    // Exponential backoff with jitter
    const exponentialDelay = Math.min(
      baseDelay * Math.pow(backoff, this.reconnectAttempts),
      maxDelay
    )
    const jitter = Math.random() * 1000 // Add random jitter up to 1 second
    return exponentialDelay + jitter
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private startHeartbeat(): void {
    this.clearHeartbeat()

    // Send ping every 30 seconds
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try {
          this.send('ping', {})
        } catch (error) {
          logger.warn('Failed to send heartbeat', { error })
        }
      }
    }, 30000)

    // Expect pong within 10 seconds
    this.resetHeartbeat()
  }

  private resetHeartbeat(): void {
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout)
    }

    this.heartbeatTimeout = setTimeout(() => {
      logger.warn('Heartbeat timeout - connection may be dead')
      this.disconnect()
      this.scheduleReconnect()
    }, 40000) // 10 seconds after the heartbeat interval
  }

  private clearHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout)
      this.heartbeatTimeout = null
    }
  }

  private setStatus(status: ConnectionStatus): void {
    if (this.status !== status) {
      this.status = status
      logger.info('WebSocket status changed', { status })
      this.statusHandlers.forEach((handler) => {
        try {
          handler(status)
        } catch (error) {
          logger.error('Error in status handler', error)
        }
      })
    }
  }
}

// Export singleton instance
export const wsClient = new WebSocketClient()
