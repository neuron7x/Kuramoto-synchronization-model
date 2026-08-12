/* Auto-generated GeoSync REST client (TypeScript). */

export type RequestOptions = {
    headers?: Record<string, string>;
    signal?: AbortSignal;
    payload?: unknown;
};

export interface ClientConfig {
    baseUrl?: string;
    defaultHeaders?: Record<string, string>;
}

export class GeoSyncClient {
    private readonly baseUrl: string;
    private readonly defaultHeaders: Record<string, string>;

    constructor(config: ClientConfig = {}) {
        this.baseUrl = (config.baseUrl || "https://api.geosync").replace(/\u002F$/, "");
        this.defaultHeaders = { ...(config.defaultHeaders || {}) };
    }

    withHeaders(headers: Record<string, string>): GeoSyncClient {
        return new GeoSyncClient({
            baseUrl: this.baseUrl,
            defaultHeaders: { ...this.defaultHeaders, ...headers },
        });
    }

    async get_market_signal(symbol: string, options: RequestOptions = {}): Promise<Response> {
        const headers = { ...this.defaultHeaders, ...(options.headers || {}) };
        const requestUrl = `${this.baseUrl}/v1/signals/${symbol}`;
        const response = await fetch(requestUrl, {
            method: "GET",
            headers,
            signal: options.signal,
        });
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        return response;
    }

    async create_prediction(options: RequestOptions = {}): Promise<Response> {
        const headers = { ...this.defaultHeaders, ...(options.headers || {}) };
        const requestUrl = `${this.baseUrl}/v1/predictions`;
        const response = await fetch(requestUrl, {
            method: "POST",
            headers,
            body: options.payload !== undefined ? JSON.stringify(options.payload) : undefined,
            signal: options.signal,
        });
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        return response;
    }
}
