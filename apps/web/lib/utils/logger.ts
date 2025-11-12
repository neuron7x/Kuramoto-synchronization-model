import { env } from '@/config/env'

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogContext {
  [key: string]: unknown
}

class Logger {
  private minLevel: LogLevel

  constructor(minLevel: LogLevel = 'info') {
    this.minLevel = minLevel
  }

  private shouldLog(level: LogLevel): boolean {
    const levels: LogLevel[] = ['debug', 'info', 'warn', 'error']
    return levels.indexOf(level) >= levels.indexOf(this.minLevel)
  }

  private formatMessage(level: LogLevel, message: string, context?: LogContext): string {
    const timestamp = new Date().toISOString()
    const contextStr = context ? ` ${JSON.stringify(context)}` : ''
    return `[${timestamp}] [${level.toUpperCase()}] ${message}${contextStr}`
  }

  debug(message: string, context?: LogContext): void {
    if (this.shouldLog('debug') && env.NEXT_PUBLIC_LOG_TO_CONSOLE) {
      // eslint-disable-next-line no-console
      console.debug(this.formatMessage('debug', message, context))
    }
  }

  info(message: string, context?: LogContext): void {
    if (this.shouldLog('info') && env.NEXT_PUBLIC_LOG_TO_CONSOLE) {
      // eslint-disable-next-line no-console
      console.info(this.formatMessage('info', message, context))
    }
  }

  warn(message: string, context?: LogContext): void {
    if (this.shouldLog('warn') && env.NEXT_PUBLIC_LOG_TO_CONSOLE) {
      console.warn(this.formatMessage('warn', message, context))
    }
  }

  error(message: string, error?: Error | unknown, context?: LogContext): void {
    if (this.shouldLog('error')) {
      const errorContext = {
        ...context,
        error:
          error instanceof Error
            ? {
                name: error.name,
                message: error.message,
                stack: error.stack,
              }
            : error,
      }

      if (env.NEXT_PUBLIC_LOG_TO_CONSOLE) {
        console.error(this.formatMessage('error', message, errorContext))
      }

      // In production, you might want to send errors to a logging service
      if (env.NEXT_PUBLIC_LOG_TO_SERVER && typeof window !== 'undefined') {
        // Send to logging endpoint
        this.sendToServer('error', message, errorContext)
      }
    }
  }

  private async sendToServer(
    level: LogLevel,
    message: string,
    context?: LogContext
  ): Promise<void> {
    try {
      await fetch('/api/logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, message, context, timestamp: new Date().toISOString() }),
      })
    } catch (error) {
      // Silently fail to avoid infinite loops
      console.error('Failed to send log to server:', error)
    }
  }
}

// Export singleton instance
export const logger = new Logger(env.NEXT_PUBLIC_LOG_LEVEL)
