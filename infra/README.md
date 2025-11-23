# Infrastructure Module

## Overview

The `infra` module contains infrastructure-related code, including database models, external service clients, and low-level system integrations.

## Purpose

- **Database Layer**: SQLAlchemy models and migrations
- **External Clients**: API clients for third-party services
- **Caching**: Redis and in-memory caching implementations
- **Message Queues**: Message broker integrations
- **File Storage**: Object storage and file system abstractions

## Key Features

- 💾 **Database ORM**: SQLAlchemy models and repositories
- 📡 **API Clients**: Type-safe clients for external APIs
- ⚡ **Caching**: Multi-layer caching strategy
- 📨 **Messaging**: Pub/sub and queue implementations
- 🗄️ **Storage**: Cloud and local storage abstractions

## Usage Examples

### Database Repository

```python
from infra.repositories import OrderRepository

repo = OrderRepository(session)

# Save order
await repo.save(order)

# Find by ID
order = await repo.find_by_id(order_id)

# Query orders
orders = await repo.find_by_symbol("BTC/USDT")
```

### Caching

```python
from infra.cache import CacheManager

cache = CacheManager()

# Set value
await cache.set("market_data:BTC", data, ttl=60)

# Get value
data = await cache.get("market_data:BTC")

# Delete
await cache.delete("market_data:BTC")
```

### Message Queue

```python
from infra.messaging import MessageBroker

broker = MessageBroker()

# Publish message
await broker.publish("orders.created", order_event)

# Subscribe to messages
@broker.subscribe("orders.created")
async def handle_order_created(event):
    print(f"Order created: {event.order_id}")
```

## Configuration

```yaml
# config/infra.yaml
infra:
  database:
    url: postgresql://user:pass@host:5432/db
    pool_size: 20
    echo: false
    
  cache:
    backend: redis
    host: localhost
    port: 6379
    ttl_seconds: 300
    
  messaging:
    broker: redis
    url: redis://localhost:6379/0
```

## Related Modules

- [`domain`](../domain/README.md): Domain models
- [`application`](../application/README.md): Application services

## Documentation

- [Infrastructure Guide](https://docs.tradepulse.io/infrastructure)

## License

See [LICENSE](../LICENSE) for licensing information.
