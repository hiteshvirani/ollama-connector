/**
 * API client for communicating with the backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:7460';

interface FetchOptions extends RequestInit {
    adminKey?: string;
}

async function fetchAPI<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
    const { adminKey, ...fetchOptions } = options;

    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(adminKey ? { 'X-Admin-Key': adminKey } : {}),
        ...options.headers,
    };

    const response = await fetch(`${API_URL}${endpoint}`, {
        ...fetchOptions,
        headers,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// Connector types
export interface Connector {
    id: string;
    name: string;
    description: string | null;
    allowed_models: string[];
    blocked_models: string[];
    priority: number;
    routing_prefer: string;
    routing_fallback: string | null;
    routing_ollama_only: boolean;
    routing_cloud_only: boolean;
    rate_limit_per_minute: number;
    rate_limit_per_hour: number;
    burst_limit: number;
    tokens_per_day: number | null;
    tokens_per_month: number | null;
    max_spend_per_day_usd: number | null;
    max_spend_per_month_usd: number | null;
    default_params: Record<string, any>;
    tags: string[];
    config_info: Record<string, any>;
    is_active: boolean;
    created_at: string;
    updated_at: string | null;
}

// Input type for creating/updating connectors (matches backend schema)
export interface ConnectorInput {
    name: string;
    description?: string;
    allowed_models?: string[];
    blocked_models?: string[];
    priority?: number;
    routing?: {
        prefer?: string;
        fallback?: string;
        ollama_only?: boolean;
        cloud_only?: boolean;
    };
    rate_limits?: {
        per_minute?: number;
        per_hour?: number;
        burst?: number;
    };
    quotas?: {
        tokens_per_day?: number;
        tokens_per_month?: number;
        max_spend_per_day_usd?: number;
        max_spend_per_month_usd?: number;
    };
    default_params?: Record<string, any>;
    tags?: string[];
    config_info?: Record<string, any>;
}

export interface ConnectorList {
    items: Connector[];
    total: number;
    page: number;
    per_page: number;
}

export interface UsageStats {
    connector_id: string;
    period: string;
    requests_total: number;
    requests_success: number;
    requests_failed: number;
    tokens_input: number;
    tokens_output: number;
    tokens_total: number;
    cost_usd: number;
    avg_latency_ms: number;
}

export interface Node {
    node_id: string;
    cloudflare_url: string | null;
    ipv4: string | null;
    ipv6: string | null;
    port: number;
    models: string[];
    load: { cpu: number; memory: number } | null;
    status: string;
    last_seen: string;
    active_jobs: number;
    failure_count: number;
}

// API functions
export const api = {
    // Connectors
    async listConnectors(adminKey: string, page = 1): Promise<ConnectorList> {
        return fetchAPI(`/api/connectors?page=${page}`, { adminKey });
    },

    async getConnector(adminKey: string, id: string): Promise<Connector> {
        return fetchAPI(`/api/connectors/${id}`, { adminKey });
    },

    async createConnector(adminKey: string, data: ConnectorInput): Promise<{ id: string; api_key: string; name: string }> {
        return fetchAPI('/api/connectors', {
            method: 'POST',
            adminKey,
            body: JSON.stringify(data),
        });
    },

    async updateConnector(adminKey: string, id: string, data: Partial<Connector>): Promise<Connector> {
        return fetchAPI(`/api/connectors/${id}`, {
            method: 'PATCH',
            adminKey,
            body: JSON.stringify(data),
        });
    },

    async deleteConnector(adminKey: string, id: string): Promise<void> {
        return fetchAPI(`/api/connectors/${id}`, { method: 'DELETE', adminKey });
    },

    async regenerateKey(adminKey: string, id: string): Promise<{ api_key: string }> {
        return fetchAPI(`/api/connectors/${id}/regenerate-key`, { method: 'POST', adminKey });
    },

    async getUsage(adminKey: string, id: string, period = 'day'): Promise<UsageStats> {
        return fetchAPI(`/api/connectors/${id}/usage?period=${period}`, { adminKey });
    },

    // Nodes
    async listNodes(adminKey: string): Promise<Node[]> {
        return fetchAPI('/api/nodes', { adminKey });
    },

    async removeNode(adminKey: string, nodeId: string): Promise<void> {
        return fetchAPI(`/api/nodes/${nodeId}`, { method: 'DELETE', adminKey });
    },

    // Health
    async healthCheck(): Promise<{ status: string }> {
        return fetchAPI('/healthz');
    },
};
