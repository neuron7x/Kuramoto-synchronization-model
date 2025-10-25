const ROUTE_NAME_PATTERN = /^[a-z0-9-]+$/i;

export class Router {
  constructor({ routes = {}, defaultRoute = 'pnl' } = {}) {
    this.routes = new Map();
    Object.entries(routes).forEach(([name, resolver]) => {
      this.register(name, resolver);
    });
    this.defaultRoute = ROUTE_NAME_PATTERN.test(defaultRoute) ? defaultRoute : 'pnl';
    this.currentRoute = this.defaultRoute;
  }

  register(name, resolver) {
    if (!ROUTE_NAME_PATTERN.test(name)) {
      throw new Error(`Invalid route name: ${name}`);
    }
    if (typeof resolver !== 'function') {
      throw new Error(`Route resolver for "${name}" must be a function`);
    }
    this.routes.set(name, resolver);
  }

  resolve(name) {
    const routeName = ROUTE_NAME_PATTERN.test(name || '') ? name : this.defaultRoute;
    if (!this.routes.has(routeName)) {
      throw new Error(`Unknown route: ${routeName}`);
    }
    const resolver = this.routes.get(routeName);
    const view = resolver();
    this.currentRoute = routeName;
    return { name: routeName, view };
  }

  navigate(name) {
    return this.resolve(name);
  }

  list() {
    return Array.from(this.routes.keys());
  }
}

export function createRouter(options) {
  return new Router(options);
}
