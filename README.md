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
- Check Docker installation
- Pull Ollama Docker image if needed
- Configure UFW firewall (allows ports 8001 and 11434 for IPv4/IPv6)
- Start Ollama service
- Pull required models (default: `llama3,mistral` - edit in setup.sh)

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

This starts two containers:
- `ollama`: official Ollama runtime (persists models in the `ollama-data` volume)
- `node`: FastAPI agent exposing `POST /execute` and sending heartbeats every 30s

Containers are configured with `restart: unless-stopped` so they come back automatically after reboots.

## How It Works

1. **Heartbeat** (`client → server`): every 30s the node posts `node_id`, current IPs, available models, metadata, and load metrics to `/nodes/heartbeat`.
2. **Registry upkeep** (`server`): the hub records the heartbeat, marks stale nodes as `offline`, and prunes entries if no heartbeat arrives for three minutes.
3. **Job submission** (`client request → server`): callers hit `POST /jobs` with `{model, prompt, options}`. The hub selects the least-busy healthy node that advertises the requested model and forwards the job to `/execute` on that node.
4. **Execution & failover** (`server ↔ node`): the node proxies the request to its local Ollama API. If a node fails or times out, the hub automatically retries with the next eligible node before returning a 503.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `SERVER_URL` | `http://localhost:8000` | Hub endpoint the node registers with. |
| `NODE_ID` | container hostname | Stable identifier reported in heartbeats. |
| `NODE_PORT` | `8001` | Port the node agent listens on. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama REST endpoint. |
| `HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeats. |
| `REQUIRED_MODELS` | `llama3,mistral` | Defined in `setup.sh` - comma-separated list of models to pull. |
| `SKIP_MODEL_PULL` | `0` | Defined in `setup.sh` - set to `"1"` to skip model pulling. |
| `HEARTBEAT_TTL_SECONDS` | `90` | Server-side grace period before marking a node offline. |
| `HEARTBEAT_OFFLINE_SECONDS` | `180` | Server-side removal window for stale nodes. |
| `NODE_MAX_FAILURES` | `3` | Failures before the hub marks a node `degraded`. |

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
