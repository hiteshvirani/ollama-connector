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

The dashboard includes:
- **Main Dashboard** (`http://localhost:8000/`): View all registered nodes, their IPv4/IPv6 addresses, status, models, load metrics, and API usage instructions
- **Request Logs** (`http://localhost:8000/static/logs.html`): Monitor all API requests, see which IP version (IPv4/IPv6) was used, node selection, success/failure status, and detailed debugging information

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
- Configure UFW firewall (allows ports 8001 and 11434 for both IPv4 and IPv6)
- Start Ollama service (systemd or background process)
- Pull required models (default: `qwen2.5:7b` - edit in setup.sh)

**Note:** The node agent listens on IPv6 (`::`) which also accepts IPv4 connections, enabling dual-stack support for maximum compatibility.

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
    "ipv4": "192.168.1.100",
    "ipv6": "2401:4900:8898:97bf:ca46:8cc3:6e3:1a5b",
    "port": 8001,
    "models": ["qwen2.5:7b", "llama3"],
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

**Note:** Nodes report both IPv4 and IPv6 addresses. The server automatically selects the best IP version for connectivity (prefers IPv6, falls back to IPv4).

#### 3. Get Specific Node

Get detailed information about a specific node:

```bash
GET /nodes/{node_id}
```

**Example:**
```bash
curl http://localhost:8000/nodes/ollama-node-1
```

#### 4. Get Request Logs

Retrieve detailed request logs for debugging and monitoring:

```bash
GET /logs?limit=100
```

**Parameters:**
- `limit` (optional): Maximum number of logs to return (default: 100)

**Response:**
```json
[
  {
    "timestamp": "2025-11-07T12:30:45.123456Z",
    "request_ip": "192.168.1.50",
    "endpoint": "/jobs",
    "method": "POST",
    "request_json": {
      "model": "qwen2.5:7b",
      "prompt": "Hello",
      "stream": false
    },
    "node_id": "ollama-node-1",
    "ip_version": "IPv6",
    "node_url": "http://[2401:4900:8898:97bf:ca46:8cc3:6e3:1a5b]:8001/execute",
    "status_code": 200,
    "success": true,
    "error": null,
    "duration_ms": 3150.5
  }
]
```

**Note:** Logs are stored in-memory and limited to the last 1000 requests. View logs in the web dashboard at `http://localhost:8000/static/logs.html` for a better UI experience.

#### 5. Submit Ollama Job (Main Endpoint)

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

1. **Heartbeat** (`client → server`): every 30s the node posts `node_id`, current IPv4/IPv6 addresses, available models, metadata, and load metrics to `/nodes/heartbeat`.
2. **Registry upkeep** (`server`): the hub records the heartbeat, marks stale nodes as `offline` after 60 seconds without heartbeat, and prunes entries if no heartbeat arrives for three minutes.
3. **Job submission** (`client request → server`): callers hit `POST /jobs` with `{model, prompt, options}`. The hub selects the least-busy healthy node that advertises the requested model and forwards the job to `/execute` on that node.
4. **IP Selection & Execution** (`server ↔ node`): The server tries IPv6 first (if available), then falls back to IPv4. This enables cross-network connectivity when both machines have global IPv6 addresses. The node proxies the request to its local Ollama API.
5. **Failover** (`server`): If a node fails or times out, the hub automatically retries with the next eligible node before returning a 503. All requests are logged with detailed information for debugging.

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
2. If IPv6 fails, the server automatically tries IPv4 (and vice versa)
3. Failed nodes are marked with an increased failure count
4. After 3 consecutive failures, a node is marked as `degraded` and won't receive new jobs
5. If all nodes fail, the API returns a 503 error with details

### IPv6 and Cross-Network Support

The system supports both IPv4 and IPv6 with intelligent IP selection:

**IPv6 Support:**
- **Global IPv6 addresses** (like `2401:...`): Publicly routable, can be accessed from **any network** with IPv6 connectivity
- **Link-local IPv6** (`fe80::...`): Only works on the same network segment
- **Unique Local Addresses** (`fc00::...`): Private network only

**IP Selection Strategy:**
1. Server tries **IPv6 first** (if available) for better cross-network connectivity
2. Falls back to **IPv4** if IPv6 fails or is not available
3. Both IP versions are tried automatically for maximum compatibility

**Cross-Network Access:**
- ✅ **Same network**: Works with both IPv4 and IPv6
- ✅ **Different networks**: Works if both machines have **global IPv6 addresses**
- ✅ **Different countries/ISPs**: Works if both have IPv6 connectivity
- ⚠️ **IPv4 only**: Limited to same network or requires NAT/port forwarding

**Requirements for Cross-Network IPv6:**
1. Both server and client must have **global IPv6 addresses** (not link-local)
2. Firewall rules must allow IPv6 connections (configured by `setup.sh`)
3. Router/ISP must support IPv6 routing
4. Both machines must have IPv6 connectivity

**Security Note:** Global IPv6 addresses are directly accessible (no NAT), so ensure firewall rules are properly configured. The `setup.sh` script configures UFW for IPv6 automatically.

## Configuration

### Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `SERVER_URL` | `http://localhost:8000` | Hub endpoint the node registers with. |
| `NODE_ID` | container hostname | Stable identifier reported in heartbeats. |
| `NODE_PORT` | `8001` | Port the node agent listens on (listens on IPv6 `::` which also accepts IPv4). |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama REST endpoint. |
| `HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeats. |
| `REQUIRED_MODELS` | `qwen2.5:7b` | Defined in `setup.sh` - comma-separated list of models to pull. |
| `SKIP_MODEL_PULL` | `0` | Defined in `setup.sh` - set to `"1"` to skip model pulling. |
| `HEARTBEAT_TTL_SECONDS` | `90` | Server-side grace period before marking a node offline. |
| `HEARTBEAT_OFFLINE_SECONDS` | `180` | Server-side removal window for stale nodes. |
| `NODE_MAX_FAILURES` | `3` | Failures before the hub marks a node `degraded`. |
| `NODE_REQUEST_TIMEOUT` | `120` | Timeout in seconds for node requests. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

### Network Configuration

**Client Node:**
- Listens on IPv6 (`::`) which also accepts IPv4 connections (dual-stack)
- Automatically detects both IPv4 and IPv6 addresses
- Reports both IPs to the server in heartbeats

**Server Hub:**
- Tries IPv6 first, then IPv4 for maximum cross-network compatibility
- Uses connection IP from heartbeat as the primary reachable address
- Supports both same-network and cross-network scenarios

**Firewall (UFW):**
- Configured automatically by `setup.sh`
- Opens ports for both IPv4 and IPv6
- Node agent port (default: 8001) and Ollama port (11434)

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

## Features

### Web Dashboard

The server provides a comprehensive web dashboard with two pages:

1. **Main Dashboard** (`http://localhost:8000/`):
   - View all registered nodes with real-time status
   - See IPv4 and IPv6 addresses for each node
   - Monitor node health, load metrics, and available models
   - View last ping time and offline detection (60 seconds threshold)
   - API usage instructions and examples
   - Dark/light theme toggle
   - Auto-refresh every 3 seconds

2. **Request Logs** (`http://localhost:8000/static/logs.html`):
   - Detailed logs of all API requests
   - Shows which IP version (IPv4/IPv6) was used
   - Node selection and dispatch information
   - Request/response details, success/failure status
   - Duration and error information
   - Search and filter capabilities
   - Auto-refresh every 3 seconds

### Request Logging

All API requests are logged with detailed information:
- Request timestamp, IP address, endpoint, and method
- Request JSON payload
- Selected node ID and IP version used (IPv4/IPv6)
- Node URL that was called
- Response status code and success/failure
- Duration in milliseconds
- Error messages (if any)

Logs are stored in-memory (last 1000 requests) and accessible via:
- Web UI: `http://localhost:8000/static/logs.html`
- API: `GET /logs?limit=100`

### IPv6 and Network Features

- **Dual-stack support**: Client listens on IPv6 (`::`) which also accepts IPv4
- **Automatic IP detection**: Client detects both IPv4 and IPv6 addresses
- **Smart IP selection**: Server tries IPv6 first, falls back to IPv4
- **Cross-network support**: Works across different networks with global IPv6
- **Connection-based IP**: Server uses connection IP for reliable reachability
- **Firewall auto-configuration**: UFW rules configured for both IPv4 and IPv6

## Troubleshooting

### Node not appearing in dashboard

1. Check if the node container is running: `docker ps | grep node`
2. Check node logs: `docker logs client-node-1`
3. Verify `SERVER_URL` is correct in the node environment
4. Check network connectivity between node and server
5. Verify firewall allows connections (check UFW status)
6. Check if node is sending heartbeats: Look for heartbeat logs in node container

### "No healthy nodes available" error

1. Check if any nodes are registered: `curl http://localhost:8000/nodes`
2. Verify nodes have the requested model available
3. Check node status - they should be `online` (not `offline` or `degraded`)
4. Ensure nodes have sent recent heartbeats (within 90 seconds)
5. Check the logs page to see why nodes might be failing

### Job execution fails

1. Check server logs: `docker logs server-hub-1`
2. Check node logs: `docker logs client-node-1`
3. Verify Ollama is running on the node: `curl http://localhost:11434/api/tags`
4. Check if the model exists on the node
5. View request logs at `http://localhost:8000/static/logs.html` to see detailed error information
6. Check which IP version was used (IPv4/IPv6) and if connectivity failed

### IPv6 connectivity issues

1. **Check IPv6 addresses:**
   ```bash
   curl http://localhost:8000/nodes | python3 -m json.tool
   ```
   Look for `ipv6` field - should show a global IPv6 address (not `fe80::` or `fc00::`)

2. **Test IPv6 connectivity:**
   ```bash
   # Get node IPv6 from /nodes endpoint, then test:
   curl http://[2401:4900:8898:97bf:ca46:8cc3:6e3:1a5b]:8001/health
   ```

3. **Check firewall:**
   ```bash
   sudo ufw status | grep 8001
   ```
   Should show rules for both IPv4 and IPv6

4. **Verify IPv6 detection:**
   ```bash
   ip -6 addr show | grep "scope global"
   ```
   Should show global IPv6 addresses (not link-local)

5. **Check logs:** View the logs page to see which IP version was attempted and why it failed

### Port conflicts

If ports 8000, 8001, or 11434 are already in use:
- Change ports in `docker-compose.yml`
- Or stop the conflicting service
- For Linux, both server and client use `network_mode: host` for direct network access

### Network connectivity between server and client

**Same Network:**
- Works with both IPv4 and IPv6
- Server automatically detects the best IP to use

**Different Networks:**
- Requires global IPv6 addresses on both machines
- IPv4 requires NAT/port forwarding or VPN
- Check firewall rules allow IPv6 connections
- Verify both machines have IPv6 connectivity: `ping6 2001:4860:4860::8888`

## Architecture Details

### Network Architecture

**Client Node:**
- Runs in Docker with `network_mode: host` for direct network access
- Listens on IPv6 (`::`) which accepts both IPv4 and IPv6 connections
- Detects IPv4 by connecting to `8.8.8.8`
- Detects IPv6 by connecting to `2001:4860:4860::8888` (Google DNS IPv6)
- Sends both IPs in heartbeat to server

**Server Hub:**
- Runs in Docker with `network_mode: host` for direct network access
- Receives heartbeats and stores connection IP (most reliable)
- Tries IPv6 first, then IPv4 when dispatching jobs
- Uses connection IP from heartbeat as primary reachable address
- Handles NAT, different networks, and cross-network scenarios

**IP Selection Logic:**
1. Server receives heartbeat with both IPv4 and IPv6
2. Connection IP (from `request.client.host`) is stored as primary
3. When dispatching: tries IPv6 first (if available), then IPv4
4. If IPv6 fails, automatically tries IPv4
5. Both IPs are preserved for maximum compatibility

### Request Flow

1. **Client sends request** → `POST /jobs` to server
2. **Server logs request** → Creates `RequestLog` entry with request details
3. **Server selects node** → Chooses best node based on load, model availability
4. **Server dispatches job** → Tries IPv6 first, then IPv4 if needed
5. **Node executes** → Proxies to local Ollama API
6. **Response returned** → Server logs success/failure and returns response
7. **Logs available** → View in dashboard or via `GET /logs` API

### Data Storage

- **In-memory registry**: Node information stored in Python dictionary
- **Thread-safe**: Uses `asyncio.Lock` for concurrent access
- **Request logs**: Stored in `collections.deque` (max 1000 entries)
- **No database**: All data is ephemeral and resets on server restart

## Next Steps

- Add authentication (API keys or mTLS) between hub and nodes
- Persist registry state in Redis/PostgreSQL for restarts
- Stream model output back to callers incrementally instead of buffered responses
- Integrate metrics and tracing for better observability
- Add rate limiting and request queuing
- Add IPv6 preference configuration option
- Support for IPv6-only networks
