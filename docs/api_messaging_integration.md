# API Messaging Integration

The API messaging integration layer connects gateway HTTP requests to the event bus
so downstream services can react to gateway traffic in a consistent way.

## GatewayRequest
- Normalizes HTTP method casing via `normalized_method()`.
- Provides case-insensitive header access with `get_header()` and exposes
  `resolved_correlation_id`, preferring explicit correlation IDs or standard
  request headers.

## IntegrationRouter
- Registers routes with `register_route`, enforcing unique names and at least one
  HTTP method.
- Matches incoming requests using full regular-expression path patterns and
  rejects unknown routes with `IntegrationRouteNotFoundError`.
- Builds event envelopes in `route_request`, encoding payloads (supporting
  dataclasses and datetime values) and assembling gateway metadata headers.
- Publishes envelopes to the configured `BaseEventBus` with `dispatch`.

## Defaults
- Partition keys default to correlation IDs, a captured `symbol` path parameter,
  or the request path.
- Payloads are JSON serialised with support for dataclasses and datetime/date
  objects.
- Headers include the method, path, optional path parameters, query string, and
  correlation identifier when provided.
