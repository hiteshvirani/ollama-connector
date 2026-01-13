# Ollama Connector

Production-ready LLM Gateway with multi-provider support (Ollama + OpenRouter).

## Quick Start

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps
```

**Services:**
| Port | Service | Description |
|------|---------|-------------|
| 7460 | Backend API | OpenAI-compatible `/v1/chat/completions` |
| 7461 | PostgreSQL | Database |
| 7462 | Redis | Rate limiting, node registry |
| 7463 | Admin Panel | Web UI for management |

## Admin Panel

1. Open http://localhost:7463
2. Enter admin key (from `.env`: `ADMIN_API_KEY`)
3. Create connectors, monitor nodes

## API Usage

```bash
# Create a connector in admin panel, then:
curl -X POST http://localhost:7460/v1/chat/completions \
  -H "Authorization: Bearer YOUR_CONNECTOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Connector Features

Each connector provides:
- **API Key**: Unique authentication
- **Priority**: 1-10 (higher = better routing)
- **Allowed Models**: Restrict which models can be used
- **Rate Limits**: Per-minute and per-hour limits
- **Routing**: Prefer Ollama (local) or OpenRouter (cloud)

## Register Ollama Nodes

```bash
cd client
export SERVER_URL="http://YOUR_SERVER:7460"
export NODE_SECRET="node-secret-from-env"
docker compose up -d
```

## Environment Variables

See `.env` for all configuration options.

## Architecture

```
Client App → Backend:7460 → Smart Router
                                ↓
                    ┌───────────┴───────────┐
                    ↓                       ↓
               Ollama Nodes            OpenRouter
```
