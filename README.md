# Ollama Connector

Coordinated server/client pair that lets a central hub dispatch Ollama model requests across multiple local machines. Each machine runs a lightweight agent that registers itself with the hub every 30 seconds, advertising its IPv4/IPv6 addresses, available models, and current load. The hub keeps this data in memory, health-checks nodes, and forwards incoming prompts to a healthy node with automatic failover.

## Structure

- `server/`: FastAPI application (`ollama-hub`) that maintains the node registry and load-balances job requests.
- `client/`: FastAPI application (`ollama-node`) installed on every Ollama host; sends heartbeats and proxies prompt execution to the local Ollama REST API.

Each folder is self-contained with its own `docker-compose.yml`.

## Quick Start

### Run the Hub

```bash
cd server
docker compose up -d
```

Hub API listens on `http://localhost:8000` by default.

**Access the Dashboard:**
Open your browser and navigate to `http://localhost:8000` to view the web dashboard showing all registered nodes, their status, available models, and system metrics.

### Run a Node

On each Ollama machine:

**Step 1: Configure and run the setup script**

Edit `setup.sh` to customize settings (optional):
```bash
cd client
# Edit setup.sh to change REQUIRED_MODELS, ports, etc.
nano setup.sh  # or your preferred editor
```

Then run the setup script:
```bash
./setup.sh
```

The setup script will:
- Check Docker installation (for node agent only)
- Install Ollama locally if not already installed
- Configure UFW firewall (allows ports 8001 and 11434 for IPv4/IPv6)
- Start Ollama service (systemd or background process)
- Pull required models (default: `qwen2.5:7b` - edit in setup.sh)

**To customize:** Edit the configuration section at the top of `setup.sh`:
- `REQUIRED_MODELS`: Change the models to pull
- `SKIP_MODEL_PULL`: Set to `"1"` to skip model pulling
- `NODE_PORT` and `OLLAMA_PORT`: Adjust ports if needed

**Step 2: Start the node agent**

```bash
export SERVER_URL="http://<hub-host>:8000"
export NODE_ID="node-$(hostname)"
docker compose up -d
```

This starts the node agent container:
- `node`: FastAPI agent exposing `POST /execute` and sending heartbeats every 30s

**Important:** Ollama must be installed and running locally (not in Docker). The setup script handles this automatically. The node agent connects to Ollama at `http://127.0.0.1:11434`.

The container is configured with `restart: unless-stopped` so it comes back automatically after reboots. Ollama service should also be configured to start on boot (handled by setup script).

## Using the Server API

The server provides a REST API to interact with Ollama models through registered nodes. All requests are automatically load-balanced across available nodes.

### Base URL

```
http://localhost:8000
```

### API Endpoints

#### 1. Health Check

Check if the server is running:

```bash
GET /healthz
```

**Response:**
```json
{"status": "ok"}
```

#### 2. List Registered Nodes

Get information about all registered nodes:

```bash
GET /nodes
```

**Response:**
```json
[
  {
    "node_id": "ollama-node-1",
    "ipv4": "172.19.0.2",
    "ipv6": null,
    "port": 8001,
    "models": ["llama3", "mistral"],
    "metadata": {"hostname": "node1"},
    "load": {
      "cpu": 0.25,
      "memory": 0.45
    },
    "last_seen": "2025-11-07T11:09:19.727166Z",
    "status": "online",
    "active_jobs": 0,
    "failure_count": 0
  }
]
```

#### 3. Get Specific Node

Get detailed information about a specific node:

```bash
GET /nodes/{node_id}
```

**Example:**
```bash
curl http://localhost:8000/nodes/ollama-node-1
```

#### 4. Submit Ollama Job (Main Endpoint)

Send a prompt to an Ollama model through any available node:

```bash
POST /jobs
Content-Type: application/json
```

**Request Body:**
```json
{
  "model": "llama3",
  "prompt": "Why is the sky blue?",
  "options": {
    "temperature": 0.7,
    "top_p": 0.9,
    "num_predict": 100
  },
  "stream": false
}
```

**Parameters:**
- `model` (required): The Ollama model identifier (e.g., "llama3", "mistral", "llama3:8b")
- `prompt` (required): The text prompt to send to the model
- `options` (optional): Additional Ollama API parameters:
  - `temperature`: Controls randomness (0.0-1.0, default varies by model)
  - `top_p`: Nucleus sampling parameter (0.0-1.0)
  - `top_k`: Top-k sampling parameter
  - `num_predict`: Maximum number of tokens to generate
  - `repeat_penalty`: Penalty for repetition (default: 1.1)
  - `seed`: Random seed for reproducibility
  - See [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) for full list
- `stream` (optional): Whether to stream the response (default: `true`)

**Response (non-streaming, `stream: false`):**
```json
{
  "model": "llama3",
  "created_at": "2025-11-07T11:15:30.123456Z",
  "response": "The sky appears blue due to a phenomenon called Rayleigh scattering...",
  "done": true,
  "context": [1, 2, 3],
  "total_duration": 1234567890,
  "load_duration": 123456,
  "prompt_eval_count": 10,
  "prompt_eval_duration": 1234567,
  "eval_count": 50,
  "eval_duration": 1111111111
}
```

**Response (streaming, `stream: true`):**
The response is streamed as Server-Sent Events (SSE) or JSON lines, depending on the Ollama API version.

### Usage Examples

#### Using cURL

**Simple request:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "prompt": "Explain quantum computing in simple terms",
    "stream": false
  }'
```

**With custom options:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "prompt": "Write a haiku about programming",
    "options": {
      "temperature": 0.8,
      "num_predict": 50
    },
    "stream": false
  }'
```

**Streaming response:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "prompt": "Tell me a story",
    "stream": true
  }'
```

#### Using Python

```python
import requests

# Server URL
SERVER_URL = "http://localhost:8000"

# Simple request
response = requests.post(
    f"{SERVER_URL}/jobs",
    json={
        "model": "llama3",
        "prompt": "What is machine learning?",
        "stream": False
    }
)

result = response.json()
print(result["response"])

# With custom options
response = requests.post(
    f"{SERVER_URL}/jobs",
    json={
        "model": "mistral",
        "prompt": "Explain neural networks",
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 200
        },
        "stream": False
    }
)

result = response.json()
print(result["response"])

# Check available nodes
nodes = requests.get(f"{SERVER_URL}/nodes").json()
print(f"Available nodes: {len(nodes)}")
for node in nodes:
    print(f"  - {node['node_id']}: {node['status']} (Models: {node['models']})")
```

#### Using JavaScript/Node.js

```javascript
const fetch = require('node-fetch'); // or use native fetch in Node 18+

const SERVER_URL = 'http://localhost:8000';

// Simple request
async function generateText() {
  const response = await fetch(`${SERVER_URL}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'llama3',
      prompt: 'Explain the concept of recursion',
      stream: false
    })
  });
  
  const result = await response.json();
  console.log(result.response);
}

// With custom options
async function generateWithOptions() {
  const response = await fetch(`${SERVER_URL}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'mistral',
      prompt: 'Write a Python function to calculate factorial',
      options: {
        temperature: 0.5,
        num_predict: 150
      },
      stream: false
    })
  });
  
  const result = await response.json();
  console.log(result.response);
}

// Check nodes
async function checkNodes() {
  const response = await fetch(`${SERVER_URL}/nodes`);
  const nodes = await response.json();
  console.log(`Available nodes: ${nodes.length}`);
  nodes.forEach(node => {
    console.log(`  - ${node.node_id}: ${node.status} (Models: ${node.models.join(', ')})`);
  });
}

generateText();
```

#### Using Python with httpx (for streaming)

```python
import httpx
import json

SERVER_URL = "http://localhost:8000"

# Streaming request
with httpx.stream(
    "POST",
    f"{SERVER_URL}/jobs",
    json={
        "model": "llama3",
        "prompt": "Write a long story about space exploration",
        "stream": True
    }
) as response:
    for line in response.iter_lines():
        if line:
            try:
                data = json.loads(line)
                if "response" in data:
                    print(data["response"], end="", flush=True)
                if data.get("done"):
                    break
            except json.JSONDecodeError:
                continue
```

### Error Handling

The API returns standard HTTP status codes:

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request format
- `503 Service Unavailable`: No healthy nodes available for the requested model, or all nodes failed

**Error Response Format:**
```json
{
  "detail": "No healthy nodes available for requested model"
}
```

Or when all nodes fail:
```json
{
  "detail": {
    "message": "All candidate nodes failed to execute the job",
    "errors": [
      {
        "node_id": "ollama-node-1",
        "message": "Connection timeout",
        "status": 503
      }
    ],
    "job_id": "123e4567-e89b-12d3-a456-426614174000"
  }
}
```

### Testing the API

**1. Check server health:**
```bash
curl http://localhost:8000/healthz
```

**2. List available nodes:**
```bash
curl http://localhost:8000/nodes | python3 -m json.tool
```

**3. Test a simple prompt:**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "prompt": "Hello, how are you?",
    "stream": false
  }' | python3 -m json.tool
```

**4. Check which models are available:**
```bash
curl http://localhost:8000/nodes | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = set()
for node in data:
    models.update(node.get('models', []))
print('Available models:', ', '.join(sorted(models)) if models else 'None')
"
```

## How It Works

1. **Heartbeat** (`client → server`): every 30s the node posts `node_id`, current IPs, available models, metadata, and load metrics to `/nodes/heartbeat`.
2. **Registry upkeep** (`server`): the hub records the heartbeat, marks stale nodes as `offline`, and prunes entries if no heartbeat arrives for three minutes.
3. **Job submission** (`client request → server`): callers hit `POST /jobs` with `{model, prompt, options}`. The hub selects the least-busy healthy node that advertises the requested model and forwards the job to `/execute` on that node.
4. **Execution & failover** (`server ↔ node`): the node proxies the request to its local Ollama API. If a node fails or times out, the hub automatically retries with the next eligible node before returning a 503.

### Load Balancing

The server automatically selects the best node for each job based on:
1. **Model availability**: Only nodes with the requested model are considered
2. **Node status**: Only `online` nodes are used
3. **Active jobs**: Nodes with fewer active jobs are preferred
4. **CPU load**: Lower CPU usage is preferred
5. **Failure count**: Nodes with fewer recent failures are preferred

### Automatic Failover

If a node fails to execute a job:
1. The server automatically tries the next best node
2. Failed nodes are marked with an increased failure count
3. After 3 consecutive failures, a node is marked as `degraded` and won't receive new jobs
4. If all nodes fail, the API returns a 503 error with details

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `SERVER_URL` | `http://localhost:8000` | Hub endpoint the node registers with. |
| `NODE_ID` | container hostname | Stable identifier reported in heartbeats. |
| `NODE_PORT` | `8001` | Port the node agent listens on. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama REST endpoint. |
| `HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeats. |
| `REQUIRED_MODELS` | `qwen2.5:7b` | Defined in `setup.sh` - comma-separated list of models to pull. |
| `SKIP_MODEL_PULL` | `0` | Defined in `setup.sh` - set to `"1"` to skip model pulling. |
| `HEARTBEAT_TTL_SECONDS` | `90` | Server-side grace period before marking a node offline. |
| `HEARTBEAT_OFFLINE_SECONDS` | `180` | Server-side removal window for stale nodes. |
| `NODE_MAX_FAILURES` | `3` | Failures before the hub marks a node `degraded`. |
| `NODE_REQUEST_TIMEOUT` | `120` | Timeout in seconds for node requests. |

Both services honour `LOG_LEVEL` for logging verbosity (`INFO` by default).

## Local Development

Install dependencies and run services directly:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt -r client/requirements.txt

# Terminal 1 (hub)
cd server
uvicorn app:app --reload --port 8000

# Terminal 2 (node)
cd client
export SERVER_URL=http://127.0.0.1:8000
uvicorn agent:app --reload --port 8001
```

## Troubleshooting

### Node not appearing in dashboard

1. Check if the node container is running: `docker ps | grep node`
2. Check node logs: `docker logs client-node-1`
3. Verify `SERVER_URL` is correct in the node environment
4. Check network connectivity between node and server

### "No healthy nodes available" error

1. Check if any nodes are registered: `curl http://localhost:8000/nodes`
2. Verify nodes have the requested model available
3. Check node status - they should be `online`
4. Ensure nodes have sent recent heartbeats (within 90 seconds)

### Job execution fails

1. Check server logs: `docker logs server-hub-1`
2. Check node logs: `docker logs client-node-1`
3. Verify Ollama is running on the node: `curl http://localhost:11434/api/tags`
4. Check if the model exists on the node

### Port conflicts

If ports 8000, 8001, or 11434 are already in use:
- Change ports in `docker-compose.yml`
- Or stop the conflicting service
- For Linux, use `172.17.0.1` instead of `host.docker.internal` for `SERVER_URL`

## Next Steps

- Add authentication (API keys or mTLS) between hub and nodes
- Persist registry state in Redis/PostgreSQL for restarts
- Stream model output back to callers incrementally instead of buffered responses
- Integrate metrics and tracing for better observability
- Add rate limiting and request queuing
