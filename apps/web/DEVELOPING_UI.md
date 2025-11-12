# TradePulse UI Development Guide

## 🎯 Overview

This guide covers development practices, patterns, and conventions for the TradePulse frontend.

## 🏗 Architecture Principles

### 1. Feature-Based Organization

Organize code by feature, not by type:

```
features/
├── markets/
│   ├── components/
│   ├── hooks/
│   └── types.ts
├── orders/
│   ├── components/
│   ├── hooks/
│   └── types.ts
└── positions/
    ├── components/
    ├── hooks/
    └── types.ts
```

### 2. Separation of Concerns

- **Components**: UI presentation only
- **Hooks**: Data fetching and state logic
- **Services**: Business logic
- **Utilities**: Pure functions

### 3. Composition Over Inheritance

Build complex UIs by composing simple components:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Market Overview</CardTitle>
  </CardHeader>
  <CardContent>
    <MarketList />
  </CardContent>
</Card>
```

## 📝 Code Style Guidelines

### TypeScript

```typescript
// ✅ DO: Use explicit types
interface Market {
  id: string
  symbol: string
  price: number
}

// ❌ DON'T: Use any
const market: any = {}

// ✅ DO: Use type guards
function isMarket(obj: unknown): obj is Market {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'symbol' in obj
  )
}

// ✅ DO: Use const assertions for literal types
const ORDER_SIDES = ['buy', 'sell'] as const
type OrderSide = typeof ORDER_SIDES[number]
```

### React Components

```tsx
// ✅ DO: Use functional components with TypeScript
interface ButtonProps {
  variant: 'primary' | 'secondary'
  onClick: () => void
  children: React.ReactNode
}

export function Button({ variant, onClick, children }: ButtonProps) {
  return (
    <button className={cn('btn', `btn-${variant}`)} onClick={onClick}>
      {children}
    </button>
  )
}

// ✅ DO: Export named components (not default)
export { Button }

// ❌ DON'T: Use default exports
// export default Button
```

### Hooks

```tsx
// ✅ DO: Prefix custom hooks with 'use'
export function useMarketData(symbol: string) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['market', symbol],
    queryFn: () => apiClient.get(`/markets/${symbol}`)
  })
  
  return { data, isLoading, error }
}

// ✅ DO: Return objects, not arrays (for better named destructuring)
const { data, isLoading } = useMarketData('BTC/USDT')

// ❌ DON'T: Return arrays for complex state
// const [data, isLoading] = useMarketData('BTC/USDT')
```

## 🎨 Styling Guidelines

### Tailwind CSS Best Practices

```tsx
// ✅ DO: Use Tailwind utility classes
<div className="flex items-center gap-4 p-6 rounded-lg bg-white shadow-sm">

// ✅ DO: Use cn() utility for conditional classes
<div className={cn(
  'btn',
  variant === 'primary' && 'bg-brand-600',
  variant === 'secondary' && 'bg-gray-600',
  isLoading && 'opacity-50 cursor-not-allowed'
)}>

// ❌ DON'T: Use inline styles
<div style={{ display: 'flex', padding: '24px' }}>

// ✅ DO: Extract complex class combinations
const buttonClasses = cn(
  'px-4 py-2 rounded-lg font-medium transition-colors',
  'hover:bg-brand-700 focus:ring-2 focus:ring-brand-600'
)
```

### Color Usage

```tsx
// Trading colors
'text-up'        // Green for positive/buy
'text-down'      // Red for negative/sell
'text-neutral'   // Gray for neutral

// Status colors
'text-brand-600' // Primary brand color
'text-gray-600'  // Secondary text
'bg-up/10'       // Light green background
'bg-down/10'     // Light red background
```

## 📊 Data Fetching Patterns

### Query Hooks

```tsx
// ✅ DO: Use TanStack Query for server state
export function useMarkets() {
  return useQuery({
    queryKey: ['markets'],
    queryFn: () => apiClient.get<Market[]>('/markets'),
    staleTime: 30 * 1000,
    refetchInterval: 30 * 1000
  })
}

// ✅ DO: Enable queries conditionally
export function useMarket(symbol: string | undefined) {
  return useQuery({
    queryKey: ['market', symbol],
    queryFn: () => apiClient.get<Market>(`/markets/${symbol}`),
    enabled: !!symbol
  })
}
```

### Mutation Hooks

```tsx
// ✅ DO: Invalidate queries after mutations
export function useCreateOrder() {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: (orderData: CreateOrderRequest) => 
      apiClient.post<Order>('/orders', orderData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    }
  })
}

// ✅ DO: Show loading and error states
function CreateOrderForm() {
  const createOrder = useCreateOrder()
  
  return (
    <form onSubmit={(e) => {
      e.preventDefault()
      createOrder.mutate(formData)
    }}>
      <Button loading={createOrder.isPending}>
        Create Order
      </Button>
      {createOrder.error && (
        <p className="text-down">{createOrder.error.message}</p>
      )}
    </form>
  )
}
```

## 🔄 State Management

### When to Use What

- **TanStack Query**: Server state (API data)
- **Zustand**: Client state (UI state, settings)
- **URL State**: Filters, pagination
- **Local State**: Form inputs, modals

### Zustand Store Pattern

```typescript
interface SettingsStore {
  theme: 'light' | 'dark'
  locale: string
  setTheme: (theme: 'light' | 'dark') => void
  setLocale: (locale: string) => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      theme: 'light',
      locale: 'en',
      setTheme: (theme) => set({ theme }),
      setLocale: (locale) => set({ locale })
    }),
    { name: 'settings' }
  )
)
```

## 🧩 Component Patterns

### Loading States

```tsx
// ✅ DO: Show skeletons during loading
function MarketList() {
  const { data, isLoading } = useMarkets()
  
  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    )
  }
  
  return (/* render data */)
}
```

### Empty States

```tsx
// ✅ DO: Provide helpful empty states
function OrdersList() {
  const { data } = useActiveOrders()
  
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="No active orders"
        description="Create your first order to get started"
        action={<Button>Create Order</Button>}
      />
    )
  }
  
  return (/* render orders */)
}
```

### Error States

```tsx
// ✅ DO: Handle errors gracefully
function MarketData({ symbol }: { symbol: string }) {
  const { data, error, refetch } = useMarket(symbol)
  
  if (error) {
    return (
      <div className="rounded-lg bg-down/10 p-4">
        <p className="text-down">Failed to load market data</p>
        <Button onClick={() => refetch()}>Retry</Button>
      </div>
    )
  }
  
  return (/* render data */)
}
```

## 🔐 Authentication Patterns

```tsx
// ✅ DO: Check authentication in components
function TradingPage() {
  const { isAuthenticated, user } = useAuth()
  
  if (!isAuthenticated) {
    return <Navigate to="/signin" />
  }
  
  return (/* trading interface */)
}

// ✅ DO: Check permissions for sensitive actions
function DeleteButton() {
  const { hasPermission } = useAuth()
  
  if (!hasPermission('orders:delete')) {
    return null
  }
  
  return <Button variant="danger">Delete</Button>
}
```

## 🧪 Testing Guidelines

### Component Tests

```tsx
import { render, screen } from '@testing-library/react'
import { Button } from '@/components/ui/button'

describe('Button', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByText('Click me')).toBeInTheDocument()
  })
  
  it('shows loading state', () => {
    render(<Button loading>Click me</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
```

### Hook Tests

```tsx
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { useMarkets } from '@/hooks/api/use-markets'

describe('useMarkets', () => {
  it('fetches markets', async () => {
    const { result } = renderHook(() => useMarkets(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      )
    })
    
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeDefined()
  })
})
```

## 🚀 Performance Tips

### Memoization

```tsx
// ✅ DO: Memoize expensive computations
const sortedOrders = useMemo(
  () => orders?.sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
  [orders]
)

// ✅ DO: Memoize callback functions
const handleCreateOrder = useCallback(
  (orderData: CreateOrderRequest) => {
    createOrder.mutate(orderData)
  },
  [createOrder]
)
```

### Code Splitting

```tsx
// ✅ DO: Lazy load heavy components
const Chart = lazy(() => import('@/components/chart'))

function MarketPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <Chart symbol="BTC/USDT" />
    </Suspense>
  )
}
```

### Virtualization

```tsx
// ✅ DO: Virtualize long lists
import { useVirtualizer } from '@tanstack/react-virtual'

function OrdersList({ orders }: { orders: Order[] }) {
  const parentRef = useRef<HTMLDivElement>(null)
  
  const virtualizer = useVirtualizer({
    count: orders.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 72
  })
  
  return (
    <div ref={parentRef} className="h-96 overflow-auto">
      {virtualizer.getVirtualItems().map((virtualRow) => (
        <OrderRow key={virtualRow.key} order={orders[virtualRow.index]} />
      ))}
    </div>
  )
}
```

## 📱 Responsive Design

```tsx
// ✅ DO: Use Tailwind responsive classes
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {/* Cards */}
</div>

// ✅ DO: Hide elements on mobile
<div className="hidden lg:block">
  <Sidebar />
</div>

// ✅ DO: Adjust spacing for mobile
<div className="p-4 md:p-6 lg:p-8">
  {/* Content */}
</div>
```

## 🌍 Internationalization

```tsx
// ✅ DO: Use translation functions
import { useTranslations } from 'next-intl'

function MarketPage() {
  const t = useTranslations('markets')
  
  return (
    <h1>{t('title')}</h1>
  )
}

// ✅ DO: Format numbers with locale
import { formatCurrency } from '@/lib/utils/format'

<span>{formatCurrency(price, 'USD', locale)}</span>
```

## 🔍 Debugging Tips

```tsx
// ✅ DO: Use React Query DevTools
// Available in development mode

// ✅ DO: Use Zustand DevTools
import { devtools } from 'zustand/middleware'

// ✅ DO: Log with context
logger.info('Order created', { orderId, symbol, side })

// ❌ DON'T: Use console.log in production code
// console.log(data)
```

## 📚 Resources

- [Next.js Documentation](https://nextjs.org/docs)
- [TanStack Query](https://tanstack.com/query)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/)
