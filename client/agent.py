"""Client-side Ollama node agent with OpenAI-compatible proxy."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
from typing import Any, Dict, Optional

import httpx
import psutil
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import Response
from pydantic import BaseModel, Field


LOGGER = logging.getLogger("ollama_node")


# Configuration
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:7460")
NODE_PORT = int(os.getenv("NODE_PORT", "8001"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
NODE_ID = os.getenv("NODE_ID", socket.gethostname())
NODE_SECRET = os.getenv("NODE_SECRET", "")
CLOUDFLARE_URL = os.getenv("CLOUDFLARE_URL", None)


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()


app = FastAPI(title="Ollama Node Agent", version="2.0.0")


# ===== Schemas =====

class LoadInfo(BaseModel):
    cpu: Optional[float] = None
    memory: Optional[float] = None


class HeartbeatPayload(BaseModel):
    node_id: str
    cloudflare_url: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    port: int = NODE_PORT
    models: list = []
    load: Optional[LoadInfo] = None
    metadata: dict = {}


# ===== Helpers =====

async def get_http_client() -> httpx.AsyncClient:
    client: Optional[httpx.AsyncClient] = getattr(app.state, "http", None)
    if client is None:
        timeout = httpx.Timeout(120.0, connect=10.0)
        client = httpx.AsyncClient(timeout=timeout)
        app.state.http = client
    return client


def detect_ipv4() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def detect_ipv6() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s:
            s.connect(("2001:4860:4860::8888", 80, 0, 0))
            return s.getsockname()[0]
    except OSError:
        return None


def gather_load_info() -> LoadInfo:
    try:
        cpu = psutil.cpu_percent(interval=None) / 100.0
    except Exception:
        cpu = None
    try:
        memory = psutil.virtual_memory().percent / 100.0
    except Exception:
        memory = None
    return LoadInfo(cpu=cpu, memory=memory)


async def fetch_available_models(http: httpx.AsyncClient) -> list[str]:
    """Fetch models from Ollama."""
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        response = await http.get(url, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        models = [item.get("name") for item in data.get("models", []) if item.get("name")]
        return models
    except Exception as exc:
        LOGGER.warning(f"Failed to fetch models: {exc}")
        return []


def get_cloudflare_url() -> Optional[str]:
    """Read Cloudflare URL from env or file."""
    cloudflare_url = os.getenv("CLOUDFLARE_URL")
    if not cloudflare_url:
        try:
            with open("/tmp/cloudflare_url.txt", "r") as f:
                cloudflare_url = f.read().strip()
        except (FileNotFoundError, IOError):
            cloudflare_url = CLOUDFLARE_URL
    return cloudflare_url


# ===== Heartbeat =====

async def send_heartbeat() -> None:
    http = await get_http_client()
    models = await fetch_available_models(http)
    load = gather_load_info()
    cloudflare_url = get_cloudflare_url()

    payload = HeartbeatPayload(
        node_id=NODE_ID,
        cloudflare_url=cloudflare_url,
        ipv4=detect_ipv4(),
        ipv6=detect_ipv6(),
        port=NODE_PORT,
        models=models,
        load=load,
        metadata={"hostname": socket.gethostname()},
    )

    url = f"{SERVER_URL.rstrip('/')}/api/nodes/heartbeat"
    headers = {"X-Node-Secret": NODE_SECRET}
    
    try:
        response = await http.post(url, json=payload.model_dump(), headers=headers)
        response.raise_for_status()
        LOGGER.debug(f"Heartbeat sent: {len(models)} models")
    except Exception as exc:
        LOGGER.error(f"Heartbeat failed: {exc}")


async def heartbeat_loop() -> None:
    await send_heartbeat()
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await send_heartbeat()


# ===== Lifecycle =====

@app.on_event("startup")
async def on_startup() -> None:
    LOGGER.info(f"Starting Ollama node agent {NODE_ID}")
    app.state.http = await get_http_client()
    app.state.heartbeat_task = asyncio.create_task(heartbeat_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    LOGGER.info(f"Stopping Ollama node agent {NODE_ID}")
    heartbeat_task: Optional[asyncio.Task] = getattr(app.state, "heartbeat_task", None)
    if heartbeat_task:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
    http: Optional[httpx.AsyncClient] = getattr(app.state, "http", None)
    if http:
        await http.aclose()


# ===== API Endpoints =====

@app.post("/v1/chat/completions")
async def chat_completions(request: Dict[str, Any]) -> Response:
    """
    OpenAI-compatible chat completions endpoint.
    Proxies to local Ollama.
    """
    http = await get_http_client()
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
    
    try:
        response = await http.post(url, json=request)
        return Response(
            content=response.content,
            media_type=response.headers.get("content-type", "application/json"),
            status_code=response.status_code
        )
    except Exception as exc:
        LOGGER.exception(f"Ollama request failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc}")


@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    """List models from local Ollama."""
    http = await get_http_client()
    models = await fetch_available_models(http)
    
    import time
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama"
            }
            for model in models
        ]
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "node_id": NODE_ID}


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}
