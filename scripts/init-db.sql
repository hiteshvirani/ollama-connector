-- ===========================================
-- Ollama Connector - Database Initialization
-- ===========================================

-- Create connectors table
CREATE TABLE IF NOT EXISTS connectors (
    id VARCHAR(50) PRIMARY KEY,
    api_key_hash VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Access control (JSONB for flexibility)
    allowed_models JSONB DEFAULT '["*"]'::jsonb,
    blocked_models JSONB DEFAULT '[]'::jsonb,
    
    -- Priority (1-10, higher = more priority)
    priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    
    -- Routing preferences
    routing_prefer VARCHAR(50) DEFAULT 'ollama',
    routing_fallback VARCHAR(50) DEFAULT 'openrouter',
    routing_ollama_only BOOLEAN DEFAULT false,
    routing_cloud_only BOOLEAN DEFAULT false,
    
    -- Rate limits
    rate_limit_per_minute INTEGER DEFAULT 60,
    rate_limit_per_hour INTEGER DEFAULT 1000,
    burst_limit INTEGER DEFAULT 20,
    
    -- Quotas
    tokens_per_day BIGINT DEFAULT NULL,
    tokens_per_month BIGINT DEFAULT NULL,
    max_spend_per_day_usd DECIMAL(10,2) DEFAULT NULL,
    max_spend_per_month_usd DECIMAL(10,2) DEFAULT NULL,
    
    -- Default parameters (JSONB)
    default_params JSONB DEFAULT '{}'::jsonb,
    
    -- Metadata
    tags JSONB DEFAULT '[]'::jsonb,
    config_info JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create usage tracking table (per connector per day)
CREATE TABLE IF NOT EXISTS connector_usage (
    id BIGSERIAL PRIMARY KEY,
    connector_id VARCHAR(50) NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Request counts
    requests_total INTEGER DEFAULT 0,
    requests_success INTEGER DEFAULT 0,
    requests_failed INTEGER DEFAULT 0,
    
    -- Token usage
    tokens_input BIGINT DEFAULT 0,
    tokens_output BIGINT DEFAULT 0,
    tokens_total BIGINT DEFAULT 0,
    
    -- Cost tracking (for paid models)
    cost_usd DECIMAL(10,4) DEFAULT 0,
    
    -- Latency stats
    avg_latency_ms DECIMAL(10,2) DEFAULT 0,
    
    -- Ensure one row per connector per day
    UNIQUE(connector_id, date)
);

-- Create request logs table (for debugging and analytics)
CREATE TABLE IF NOT EXISTS request_logs (
    id BIGSERIAL PRIMARY KEY,
    connector_id VARCHAR(50) REFERENCES connectors(id) ON DELETE SET NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Request info
    model VARCHAR(100),
    provider VARCHAR(50),  -- 'ollama', 'openrouter', etc.
    node_id VARCHAR(100),  -- Which Ollama node was used
    
    -- Token usage
    tokens_input INTEGER,
    tokens_output INTEGER,
    
    -- Performance
    latency_ms INTEGER,
    
    -- Status
    status VARCHAR(20),  -- 'success', 'error', 'rate_limited', etc.
    error TEXT,
    
    -- Request/response (optional, can be large)
    request_body JSONB,
    response_body JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_connectors_api_key_hash ON connectors(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_connectors_is_active ON connectors(is_active);
CREATE INDEX IF NOT EXISTS idx_usage_connector_date ON connector_usage(connector_id, date);
CREATE INDEX IF NOT EXISTS idx_logs_connector ON request_logs(connector_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON request_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_model ON request_logs(model);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for connectors table
DROP TRIGGER IF EXISTS update_connectors_updated_at ON connectors;
CREATE TRIGGER update_connectors_updated_at
    BEFORE UPDATE ON connectors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert a default admin connector for testing
INSERT INTO connectors (
    id, 
    api_key_hash, 
    name, 
    description, 
    priority,
    allowed_models,
    rate_limit_per_minute,
    rate_limit_per_hour
) VALUES (
    'conn_default',
    -- SHA256 hash of 'sk-conn-default-test-key-12345678'
    '8f14e45fceea167a5a36dedd4bea2543',
    'Default Test Connector',
    'Default connector for testing. API Key: sk-conn-default-test-key-12345678',
    5,
    '["*"]'::jsonb,
    100,
    1000
) ON CONFLICT (id) DO NOTHING;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Ollama Connector database initialized successfully!';
END $$;
