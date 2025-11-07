"""Client-side Ollama node agent implemented with FastAPI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
from typing import Any, Dict, Optional

import httpx
import psutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from schemas import HeartbeatPayload, JobDispatchPayload, LoadInfo


LOGGER = logging.getLogger("ollama_node")


DEFAULT_SERVER_URL = "http://localhost:8000"
NODE_PORT = int(os.getenv("NODE_PORT", "8001"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
SERVER_URL = os.getenv("SERVER_URL", DEFAULT_SERVER_URL)
NODE_ID = os.getenv("NODE_ID", socket.gethostname())


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()


app = FastAPI(title="Ollama Node Agent", version="0.1.0")


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
    except Exception:  # noqa: BLE001
        cpu = None
    try:
        memory = psutil.virtual_memory().percent / 100.0
    except Exception:  # noqa: BLE001
        memory = None
    return LoadInfo(cpu=cpu, memory=memory)


async def fetch_available_models(http: httpx.AsyncClient) -> list[str]:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    max_retries = 3
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            response = await http.get(url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
            models = []
            for item in data.get("models", []):
                name = item.get("name")
                if name:
                    models.append(name)
            
            if models:
                LOGGER.debug("Found %d models: %s", len(models), ", ".join(models))
            else:
                LOGGER.warning("Ollama returned no models. Make sure models are pulled.")
            
            return models
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                LOGGER.debug("Ollama API timeout, retrying in %.1fs...", retry_delay)
                await asyncio.sleep(retry_delay)
                continue
            LOGGER.warning("Failed to fetch models from Ollama: timeout after %d attempts", max_retries)
            return []
        except Exception as exc:  # noqa: BLE001
            if attempt < max_retries - 1:
                LOGGER.debug("Failed to fetch models (attempt %d/%d): %s, retrying...", attempt + 1, max_retries, exc)
                await asyncio.sleep(retry_delay)
                continue
            LOGGER.warning("Failed to fetch models from Ollama after %d attempts: %s", max_retries, exc)
            return []
    
    return []


async def send_heartbeat() -> None:
    http = await get_http_client()

    models = await fetch_available_models(http)
    load = gather_load_info()

    payload = HeartbeatPayload(
        node_id=NODE_ID,
        ipv4=detect_ipv4(),
        ipv6=detect_ipv6(),
        port=NODE_PORT,
        models=models,
        load=load,
        metadata={"hostname": socket.gethostname()},
    )

    url = f"{SERVER_URL.rstrip('/')}/nodes/heartbeat"
    try:
        response = await http.post(url, json=payload.model_dump())
        response.raise_for_status()
        LOGGER.debug("Heartbeat acknowledged by server: %s", response.json())
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Heartbeat failed: %s", exc)


async def heartbeat_loop() -> None:
    # Send an initial heartbeat immediately on startup.
    await send_heartbeat()

    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await send_heartbeat()


@app.on_event("startup")
async def on_startup() -> None:  # pragma: no cover - lifecycle hook
    LOGGER.info("Starting Ollama node agent %s", NODE_ID)
    app.state.http = await get_http_client()
    app.state.heartbeat_task = asyncio.create_task(heartbeat_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:  # pragma: no cover - lifecycle hook
    LOGGER.info("Stopping Ollama node agent %s", NODE_ID)
    heartbeat_task: Optional[asyncio.Task] = getattr(app.state, "heartbeat_task", None)
    if heartbeat_task:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
    http: Optional[httpx.AsyncClient] = getattr(app.state, "http", None)
    if http:
        await http.aclose()


async def execute_with_ollama(job: JobDispatchPayload) -> httpx.Response:
    http = await get_http_client()
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload: Dict[str, Any] = {"model": job.model, "prompt": job.prompt, "stream": job.stream}
    if job.options:
        payload.update({k: v for k, v in job.options.items() if k not in {"model", "prompt"}})
    try:
        response = await http.post(url, json=payload)
        response.raise_for_status()
        return response
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Ollama request failed for job %s", job.job_id)
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc}") from exc


@app.post("/execute")
async def execute(job: JobDispatchPayload) -> Response:
    LOGGER.info("Received job %s targeting model %s", job.job_id, job.model)
    response = await execute_with_ollama(job)
    media_type = response.headers.get("content-type", "application/json")
    return Response(content=response.content, media_type=media_type, status_code=response.status_code)


@app.get("/health")
async def health() -> Dict[str, str]:  # pragma: no cover - trivial endpoint
    return {"status": "ok", "node_id": NODE_ID}


