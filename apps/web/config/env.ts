import { z } from 'zod'

// Schema for environment variables validation
const envSchema = z.object({
  // Environment
  NODE_ENV: z.enum(['development', 'staging', 'production']).default('development'),
  NEXT_PUBLIC_APP_ENV: z.enum(['development', 'staging', 'production']).default('development'),

  // API Configuration
  NEXT_PUBLIC_API_BASE_URL: z.string().url().default('http://localhost:8000'),
  NEXT_PUBLIC_WS_URL: z.string().default('ws://localhost:8000/ws'),
  NEXT_PUBLIC_API_TIMEOUT: z.coerce.number().default(30000),

  // Authentication
  NEXT_PUBLIC_AUTH_ISSUER: z.string().optional(),
  NEXT_PUBLIC_AUTH_CLIENT_ID: z.string().optional(),
  NEXT_PUBLIC_AUTH_REDIRECT_URI: z.string().optional(),
  NEXT_PUBLIC_AUTH_SCOPE: z.string().default('openid profile email trading'),

  JWT_SECRET: z.string().min(32).optional(),
  JWT_EXPIRATION: z.string().default('24h'),
  REFRESH_TOKEN_EXPIRATION: z.string().default('7d'),

  SESSION_SECRET: z.string().min(32).optional(),
  SESSION_MAX_AGE: z.coerce.number().default(86400),

  // Feature Flags
  NEXT_PUBLIC_FEATURE_ADVANCED_CHARTS: z.coerce.boolean().default(true),
  NEXT_PUBLIC_FEATURE_PAPER_TRADING: z.coerce.boolean().default(true),
  NEXT_PUBLIC_FEATURE_SOCIAL_TRADING: z.coerce.boolean().default(false),
  NEXT_PUBLIC_FEATURE_AI_SIGNALS: z.coerce.boolean().default(false),
  NEXT_PUBLIC_FEATURE_STRATEGY_BUILDER: z.coerce.boolean().default(true),
  NEXT_PUBLIC_FEATURE_ALERTS: z.coerce.boolean().default(true),
  NEXT_PUBLIC_FEATURE_EXPORT_DATA: z.coerce.boolean().default(true),

  // Observability
  NEXT_PUBLIC_SENTRY_DSN: z.string().optional(),
  SENTRY_ORG: z.string().optional(),
  SENTRY_PROJECT: z.string().optional(),
  SENTRY_AUTH_TOKEN: z.string().optional(),
  SENTRY_ENVIRONMENT: z.string().default('development'),
  NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE: z.coerce.number().default(1.0),
  NEXT_PUBLIC_SENTRY_REPLAYS_SESSION_SAMPLE_RATE: z.coerce.number().default(0.1),
  NEXT_PUBLIC_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE: z.coerce.number().default(1.0),

  // Analytics
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_HOST: z.string().url().optional(),
  NEXT_PUBLIC_AMPLITUDE_API_KEY: z.string().optional(),
  NEXT_PUBLIC_GOOGLE_ANALYTICS_ID: z.string().optional(),

  // Logging
  NEXT_PUBLIC_LOG_LEVEL: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
  NEXT_PUBLIC_LOG_TO_CONSOLE: z.coerce.boolean().default(true),
  NEXT_PUBLIC_LOG_TO_SERVER: z.coerce.boolean().default(false),

  // WebSocket
  NEXT_PUBLIC_WS_RECONNECT_DELAY: z.coerce.number().default(1000),
  NEXT_PUBLIC_WS_MAX_RECONNECT_DELAY: z.coerce.number().default(30000),
  NEXT_PUBLIC_WS_RECONNECT_BACKOFF: z.coerce.number().default(1.5),
  NEXT_PUBLIC_WS_MAX_RECONNECT_ATTEMPTS: z.coerce.number().default(10),

  // Real-time Data
  NEXT_PUBLIC_POLLING_INTERVAL: z.coerce.number().default(5000),
  NEXT_PUBLIC_MARKET_DATA_REFRESH: z.coerce.number().default(1000),
  NEXT_PUBLIC_POSITION_REFRESH: z.coerce.number().default(3000),
  NEXT_PUBLIC_ORDER_REFRESH: z.coerce.number().default(2000),

  // Trading
  NEXT_PUBLIC_DEFAULT_LEVERAGE: z.coerce.number().default(1),
  NEXT_PUBLIC_MAX_LEVERAGE: z.coerce.number().default(10),
  NEXT_PUBLIC_MIN_ORDER_SIZE: z.coerce.number().default(0.001),
  NEXT_PUBLIC_PRICE_PRECISION: z.coerce.number().default(2),
  NEXT_PUBLIC_QUANTITY_PRECISION: z.coerce.number().default(6),

  // UI/UX
  NEXT_PUBLIC_DEFAULT_LOCALE: z.string().default('en'),
  NEXT_PUBLIC_SUPPORTED_LOCALES: z.string().default('en,uk,de,fr,es,ja,zh'),
  NEXT_PUBLIC_DEFAULT_TIMEZONE: z.string().default('UTC'),
  NEXT_PUBLIC_DEFAULT_THEME: z.enum(['light', 'dark', 'system']).default('light'),
  NEXT_PUBLIC_CURRENCY_FORMAT: z.string().default('USD'),
  NEXT_PUBLIC_DATE_FORMAT: z.string().default('YYYY-MM-DD HH:mm:ss'),

  // Table
  NEXT_PUBLIC_DEFAULT_PAGE_SIZE: z.coerce.number().default(20),
  NEXT_PUBLIC_MAX_PAGE_SIZE: z.coerce.number().default(100),
  NEXT_PUBLIC_ENABLE_VIRTUALIZATION: z.coerce.boolean().default(true),

  // Chart
  NEXT_PUBLIC_CHART_THEME: z.enum(['light', 'dark']).default('light'),
  NEXT_PUBLIC_DEFAULT_TIMEFRAME: z.string().default('1h'),
  NEXT_PUBLIC_CHART_UPDATE_INTERVAL: z.coerce.number().default(1000),

  // Performance
  NEXT_PUBLIC_ENABLE_SERVICE_WORKER: z.coerce.boolean().default(false),
  NEXT_PUBLIC_CACHE_STRATEGY: z
    .enum(['cache-first', 'network-first', 'stale-while-revalidate'])
    .default('cache-first'),
  NEXT_PUBLIC_PRELOAD_MARKET_DATA: z.coerce.boolean().default(true),

  // Security
  CSRF_SECRET: z.string().min(32).optional(),
  NEXT_PUBLIC_API_RATE_LIMIT: z.coerce.number().default(100),
  NEXT_PUBLIC_API_RATE_LIMIT_WINDOW: z.coerce.number().default(60000),
  NEXT_PUBLIC_CSP_REPORT_URI: z.string().optional(),

  // Development
  NEXT_PUBLIC_ENABLE_DEVTOOLS: z.coerce.boolean().default(true),
  NEXT_PUBLIC_ENABLE_MOCK_API: z.coerce.boolean().default(false),
  NEXT_PUBLIC_MOCK_DELAY: z.coerce.number().default(500),

  // Build
  ANALYZE_BUNDLE: z.coerce.boolean().default(false),
  SOURCE_MAPS: z.coerce.boolean().default(true),
})

export type Env = z.infer<typeof envSchema>

// Validate and parse environment variables
function validateEnv(): Env {
  try {
    return envSchema.parse(process.env)
  } catch (error) {
    if (error instanceof z.ZodError) {
      const missingVars = error.issues
        .map((err: z.ZodIssue) => `${err.path.join('.')}: ${err.message}`)
        .join('\n')
      throw new Error(`Environment validation failed:\n${missingVars}`)
    }
    throw error
  }
}

// Singleton instance
let envInstance: Env | null = null

export function getEnv(): Env {
  if (!envInstance) {
    envInstance = validateEnv()
  }
  return envInstance
}

// Export validated config
export const env = getEnv()

// Helper to check if we're in development
export const isDevelopment = env.NODE_ENV === 'development'
export const isProduction = env.NODE_ENV === 'production'
export const isStaging = env.NODE_ENV === 'staging'

// Feature flags helper
export const features = {
  advancedCharts: env.NEXT_PUBLIC_FEATURE_ADVANCED_CHARTS,
  paperTrading: env.NEXT_PUBLIC_FEATURE_PAPER_TRADING,
  socialTrading: env.NEXT_PUBLIC_FEATURE_SOCIAL_TRADING,
  aiSignals: env.NEXT_PUBLIC_FEATURE_AI_SIGNALS,
  strategyBuilder: env.NEXT_PUBLIC_FEATURE_STRATEGY_BUILDER,
  alerts: env.NEXT_PUBLIC_FEATURE_ALERTS,
  exportData: env.NEXT_PUBLIC_FEATURE_EXPORT_DATA,
}

// API configuration
export const apiConfig = {
  baseUrl: env.NEXT_PUBLIC_API_BASE_URL,
  wsUrl: env.NEXT_PUBLIC_WS_URL,
  timeout: env.NEXT_PUBLIC_API_TIMEOUT,
  rateLimit: env.NEXT_PUBLIC_API_RATE_LIMIT,
  rateLimitWindow: env.NEXT_PUBLIC_API_RATE_LIMIT_WINDOW,
}

// WebSocket configuration
export const wsConfig = {
  url: env.NEXT_PUBLIC_WS_URL,
  reconnectDelay: env.NEXT_PUBLIC_WS_RECONNECT_DELAY,
  maxReconnectDelay: env.NEXT_PUBLIC_WS_MAX_RECONNECT_DELAY,
  reconnectBackoff: env.NEXT_PUBLIC_WS_RECONNECT_BACKOFF,
  maxReconnectAttempts: env.NEXT_PUBLIC_WS_MAX_RECONNECT_ATTEMPTS,
}
