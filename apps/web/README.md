# TradePulse Web UI

Modern, production-ready trading platform frontend built with Next.js 14, TypeScript, and Tailwind CSS.

## 🚀 Quick Start

```bash
# Install dependencies
npm ci

# Start development server
npm run dev

# Build for production
npm run build

# Start production server
npm start

# Run tests
npm test
npm run test:playwright
```

## 📁 Project Structure

```
apps/web/
├── app/                      # Next.js App Router
│   ├── (protected)/         # Protected routes (require auth)
│   ├── (public)/            # Public routes
│   ├── api/                 # API routes
│   ├── layout.tsx           # Root layout
│   └── providers.tsx        # Global providers
├── components/
│   ├── auth/                # Authentication components
│   └── ui/                  # Reusable UI components
├── config/                  # Configuration
│   └── env.ts              # Environment validation (Zod)
├── hooks/
│   ├── api/                # TanStack Query hooks
│   ├── use-auth.ts         # Authentication hook
│   └── ...                 # Other custom hooks
├── lib/
│   ├── api/                # API client
│   ├── auth/               # Authentication service
│   ├── utils/              # Utility functions
│   └── websocket/          # WebSocket client
├── stores/                 # Zustand global stores
├── types/                  # TypeScript type definitions
├── public/                 # Static assets
└── styles/                 # Global styles

```

## 🛠 Tech Stack

### Core
- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe JavaScript (strict mode)
- **Tailwind CSS** - Utility-first CSS framework
- **MUI** - Material-UI component library

### State Management
- **TanStack Query** - Server state management
- **Zustand** - Client state management

### Data Fetching
- **Custom API Client** - With retry, timeout, correlation IDs
- **WebSocket Client** - Auto-reconnect, exponential backoff

### Forms & Validation
- **React Hook Form** - Performant forms
- **Zod** - Schema validation

### Charts & Visualization
- **Lightweight Charts** - Financial charts
- **Recharts** - General-purpose charts

### Development
- **ESLint** - Code linting
- **Prettier** - Code formatting
- **Husky** - Git hooks
- **lint-staged** - Pre-commit linting

## 🔐 Authentication

The app uses JWT-based authentication with refresh tokens:

```tsx
import { useAuth } from '@/hooks/use-auth'

function MyComponent() {
  const { user, isAuthenticated, login, logout } = useAuth()
  
  // Use authentication state and methods
}
```

### Protected Routes

```tsx
import { ProtectedRoute } from '@/components/auth/protected-route'

export default function Page() {
  return (
    <ProtectedRoute requiredRole="trader">
      {/* Your protected content */}
    </ProtectedRoute>
  )
}
```

### Permission Guards

```tsx
import { PermissionGuard } from '@/components/auth/permission-guard'

<PermissionGuard permission="trading:create_order">
  <Button>Create Order</Button>
</PermissionGuard>
```

## 📊 Data Fetching

### Using API Hooks

```tsx
import { useMarkets, useMarket } from '@/hooks/api/use-markets'
import { useActiveOrders, useCreateOrder } from '@/hooks/api/use-orders'
import { usePositions } from '@/hooks/api/use-positions'

function TradingDashboard() {
  // Fetch data
  const { data: markets, isLoading } = useMarkets()
  const { data: orders } = useActiveOrders()
  const { data: positions } = usePositions()
  
  // Mutations
  const createOrder = useCreateOrder()
  
  const handleCreateOrder = () => {
    createOrder.mutate({
      symbol: 'BTC/USDT',
      side: 'buy',
      type: 'limit',
      quantity: 0.1,
      price: 50000
    })
  }
  
  return (/* Your UI */)
}
```

### WebSocket Connection

```tsx
import { wsClient, ConnectionStatus } from '@/lib/websocket/client'

// Connect
wsClient.connect()

// Subscribe to messages
const unsubscribe = wsClient.subscribe('market_update', (message) => {
  console.log('Market update:', message.data)
})

// Send message
wsClient.send('subscribe', { symbols: ['BTC/USDT'] })

// Check status
const isConnected = wsClient.isConnected()

// Disconnect
wsClient.disconnect()

// Cleanup
unsubscribe()
```

## 🎨 UI Components

### Button

```tsx
import { Button } from '@/components/ui/button'

<Button variant="primary" size="md" loading={false}>
  Click Me
</Button>
```

Variants: `primary`, `secondary`, `outline`, `ghost`, `danger`  
Sizes: `sm`, `md`, `lg`

### Card

```tsx
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>
    Content goes here
  </CardContent>
</Card>
```

### Badge

```tsx
import { Badge } from '@/components/ui/badge'

<Badge variant="success">Active</Badge>
<Badge variant="danger">Error</Badge>
```

Variants: `default`, `success`, `warning`, `danger`, `info`

## ⚙️ Configuration

### Environment Variables

Copy `.env.example` to `.env.local` and configure:

```bash
# API Configuration
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws

# Authentication
JWT_SECRET=your-secret-key
SESSION_SECRET=your-session-secret

# Feature Flags
NEXT_PUBLIC_FEATURE_ADVANCED_CHARTS=true
NEXT_PUBLIC_FEATURE_PAPER_TRADING=true

# Observability
NEXT_PUBLIC_SENTRY_DSN=
NEXT_PUBLIC_POSTHOG_KEY=
```

All environment variables are validated at runtime using Zod schemas.

## 🧪 Testing

### Unit Tests (Jest)

```bash
npm test                  # Run once
npm run test:watch        # Watch mode
```

### E2E Tests (Playwright)

```bash
npm run test:playwright   # Run all E2E tests
```

## 🏗 Building for Production

```bash
# Build
npm run build

# The build creates:
# - .next/standalone/     # Standalone server
# - .next/static/         # Static assets
# - .next/standalone.tar  # Production package
```

### Docker Build

```bash
# Build image
docker build -t tradepulse-ui:latest .

# Run container
docker run -p 3000:3000 tradepulse-ui:latest
```

### Docker Compose

```bash
# Start all services
docker-compose up -d

# UI is available at http://localhost:3000
```

## 🔍 Code Quality

### Linting

```bash
npm run lint              # Check for issues
npm run lint:fix          # Auto-fix issues
```

### Formatting

```bash
npm run format            # Format all files
npm run format:check      # Check formatting
```

### Type Checking

```bash
npm run typecheck         # TypeScript type check
```

### Pre-commit Hooks

Husky and lint-staged automatically run linting and formatting on staged files before commit.

## 📈 Performance

### Bundle Analysis

```bash
ANALYZE_BUNDLE=true npm run build
```

### Current Metrics
- **First Load JS**: ~213 kB
- **Lighthouse Score**: TBD
- **Core Web Vitals**: TBD

## 🔐 Security

- **CSP Headers**: Configured in `next.config.js`
- **CORS**: Handled in middleware
- **XSS Protection**: React's built-in escaping
- **CSRF**: Token validation for state-changing operations
- **Dependencies**: Regular `npm audit` checks

## 📚 Additional Documentation

- [DEVELOPING_UI.md](./DEVELOPING_UI.md) - Development guidelines
- [DESIGN_GUIDE.md](./DESIGN_GUIDE.md) - Design system
- [API.md](./API.md) - API documentation

## 🤝 Contributing

1. Follow the TypeScript strict mode guidelines
2. Use existing components and utilities
3. Write tests for new features
4. Run linting and formatting before commit
5. Keep commits focused and atomic

## 📝 License

See [LICENSE](../../LICENSE) in repository root.
