"""FastAPI application acting as the Ollama orchestrator server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from schemas import HeartbeatPayload, JobDispatchPayload, JobRequest, NodeInfo


LOGGER = logging.getLogger("ollama_hub")


HEARTBEAT_TTL_SECONDS = int(os.getenv("HEARTBEAT_TTL_SECONDS", "90"))
HEARTBEAT_OFFLINE_SECONDS = int(os.getenv("HEARTBEAT_OFFLINE_SECONDS", "180"))
NODE_MAX_FAILURES = int(os.getenv("NODE_MAX_FAILURES", "3"))
NODE_REQUEST_TIMEOUT = float(os.getenv("NODE_REQUEST_TIMEOUT", "120"))


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()


@dataclass
class NodeState:
    """Internal bookkeeping for a registered node."""

    record: NodeInfo
    active_jobs: int = 0
    failure_count: int = 0

    def bump_heartbeat(self, payload: HeartbeatPayload) -> None:
        merged = payload.model_dump()
        merged["last_seen"] = datetime.now(timezone.utc)
        merged["status"] = "online"
        self.record = self.record.copy(update=merged)
        self.failure_count = 0

    def to_dict(self) -> Dict[str, object]:
        data = self.record.model_dump()
        data["active_jobs"] = self.active_jobs
        data["failure_count"] = self.failure_count
        return data


class NodeDispatchError(RuntimeError):
    """Raised when a node fails to execute a dispatched job."""

    def __init__(self, node_id: str, message: str, status_code: int):
        super().__init__(message)
        self.node_id = node_id
        self.status_code = status_code


def create_app() -> FastAPI:
    app = FastAPI(title="Ollama Hub", version="0.1.0")

    app.state.registry: Dict[str, NodeState] = {}
    app.state.registry_lock = asyncio.Lock()
    app.state.http: Optional[httpx.AsyncClient] = None
    app.state.cleanup_task: Optional[asyncio.Task] = None

    # Mount static files for dashboard
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.on_event("startup")
    async def on_startup() -> None:  # pragma: no cover - lifecycle hook
        LOGGER.info("Starting Ollama Hub server")
        timeout = httpx.Timeout(
            NODE_REQUEST_TIMEOUT,
            connect=10.0,
            read=NODE_REQUEST_TIMEOUT,
            write=NODE_REQUEST_TIMEOUT,
            pool=NODE_REQUEST_TIMEOUT,
        )
        app.state.http = httpx.AsyncClient(timeout=timeout)
        app.state.cleanup_task = asyncio.create_task(_cleanup_loop(app))

    @app.on_event("shutdown")
    async def on_shutdown() -> None:  # pragma: no cover - lifecycle hook
        LOGGER.info("Shutting down Ollama Hub server")
        if app.state.cleanup_task:
            app.state.cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app.state.cleanup_task
        if app.state.http:
            await app.state.http.aclose()

    async def registry_snapshot() -> Dict[str, NodeState]:
        async with app.state.registry_lock:
            return dict(app.state.registry)

    def build_node_base(node: NodeInfo) -> str:
        host = node.ipv4 or node.ipv6
        if not host:
            raise ValueError("Node has no reachable IP address")
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"http://{host}:{node.port}"

    async def mark_job_start(node_id: str) -> None:
        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if entry:
                entry.active_jobs += 1

    async def mark_job_end(node_id: str, success: bool) -> None:
        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if not entry:
                return
            entry.active_jobs = max(entry.active_jobs - 1, 0)
            if success:
                entry.failure_count = 0
                if entry.record.status != "online":
                    entry.record = entry.record.copy(update={"status": "online"})
                return
            entry.failure_count += 1
            if entry.failure_count >= NODE_MAX_FAILURES:
                LOGGER.warning("Marking node %s as degraded after %s failures", node_id, entry.failure_count)
                entry.record = entry.record.copy(update={"status": "degraded"})

    async def choose_node_ids(model: str) -> List[str]:
        async with app.state.registry_lock:
            candidates = [
                (node_id, entry)
                for node_id, entry in app.state.registry.items()
                if model in entry.record.models and entry.record.status == "online"
            ]
        candidates.sort(
            key=lambda item: (
                item[1].active_jobs,
                (item[1].record.load.cpu if item[1].record.load and item[1].record.load.cpu is not None else 1.0),
                item[1].failure_count,
            )
        )
        return [node_id for node_id, _ in candidates]

    async def snapshot_node(node_id: str) -> Optional[NodeInfo]:
        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if not entry:
                return None
            return entry.record.copy(deep=True)

    async def dispatch_to_node(node_id: str, payload: JobDispatchPayload) -> Response:
        http = app.state.http
        if http is None:  # pragma: no cover - startup invariant
            raise RuntimeError("HTTP client not initialised")

        node_snapshot = await snapshot_node(node_id)
        if not node_snapshot:
            raise NodeDispatchError(node_id, "Node disappeared before dispatch", status_code=410)

        base_url = build_node_base(node_snapshot)
        target_url = f"{base_url}/execute"
        LOGGER.info("Dispatching job %s to node %s (%s)", payload.job_id, node_id, target_url)

        await mark_job_start(node_id)
        try:
            response = await http.post(target_url, json=payload.model_dump())
        except Exception as exc:  # noqa: BLE001
            await mark_job_end(node_id, success=False)
            raise NodeDispatchError(node_id, f"Request failed: {exc}", status_code=503) from exc

        success = 200 <= response.status_code < 300
        await mark_job_end(node_id, success=success)

        if not success:
            message = response.text or response.reason_phrase
            raise NodeDispatchError(node_id, message, status_code=response.status_code)

        media_type = response.headers.get("content-type", "application/json")
        return Response(content=response.content, media_type=media_type, status_code=response.status_code)

    async def _cleanup_loop(app_: FastAPI) -> None:
        try:
            ttl = timedelta(seconds=HEARTBEAT_TTL_SECONDS)
            offline_after = timedelta(seconds=HEARTBEAT_OFFLINE_SECONDS)
            while True:
                await asyncio.sleep(HEARTBEAT_TTL_SECONDS // 2 or 30)
                now = datetime.now(timezone.utc)
                async with app_.state.registry_lock:
                    for node_id, entry in list(app_.state.registry.items()):
                        delta = now - entry.record.last_seen
                        if delta > offline_after:
                            LOGGER.warning("Removing node %s after %s without heartbeat", node_id, delta)
                            app_.state.registry.pop(node_id)
                            continue
                        if delta > ttl and entry.record.status != "offline":
                            LOGGER.warning("Marking node %s offline after %s without heartbeat", node_id, delta)
                            entry.record = entry.record.copy(update={"status": "offline"})
        except asyncio.CancelledError:  # pragma: no cover - shutdown behaviour
            LOGGER.debug("Cleanup loop cancelled")

    @app.post("/nodes/heartbeat")
    async def register_node(payload: HeartbeatPayload, request: Request) -> Dict[str, object]:
        remote_host = request.client.host if request.client else None

        payload_data = payload.model_dump()
        if not payload_data.get("ipv4") and remote_host and ":" not in remote_host:
            payload_data["ipv4"] = remote_host
        if not payload_data.get("ipv6") and remote_host and ":" in remote_host:
            payload_data["ipv6"] = remote_host

        payload = HeartbeatPayload(**payload_data)
        node_id = payload.node_id

        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if entry:
                entry.bump_heartbeat(payload)
                LOGGER.debug("Updated heartbeat for node %s", node_id)
            else:
                record = NodeInfo(**payload.model_dump(), last_seen=datetime.now(timezone.utc), status="online")
                app.state.registry[node_id] = NodeState(record=record)
                LOGGER.info("Registered new node %s", node_id)

        return {"node_id": node_id, "status": "ok"}

    @app.get("/nodes")
    async def list_nodes() -> List[Dict[str, object]]:
        snapshot = await registry_snapshot()
        return [state.to_dict() for state in snapshot.values()]

    @app.get("/nodes/{node_id}")
    async def get_node(node_id: str) -> Dict[str, object]:
        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if not entry:
                raise HTTPException(status_code=404, detail="Node not found")
            return entry.to_dict()

    @app.post("/jobs")
    async def create_job(request_payload: JobRequest) -> Response:
        candidate_ids = await choose_node_ids(request_payload.model)
        if not candidate_ids:
            raise HTTPException(status_code=503, detail="No healthy nodes available for requested model")

        job_id = str(uuid4())
        dispatch_payload = JobDispatchPayload(
            job_id=job_id,
            model=request_payload.model,
            prompt=request_payload.prompt,
            options=request_payload.options,
            stream=request_payload.stream,
        )

        errors = []
        for node_id in candidate_ids:
            try:
                return await dispatch_to_node(node_id, dispatch_payload)
            except NodeDispatchError as exc:
                LOGGER.warning("Node %s failed job %s: %s", exc.node_id, job_id, exc)
                errors.append({"node_id": exc.node_id, "message": str(exc), "status": exc.status_code})
                continue

        detail = {
            "message": "All candidate nodes failed to execute the job",
            "errors": errors,
            "job_id": job_id,
        }
        raise HTTPException(status_code=503, detail=detail)

    @app.get("/healthz")
    async def healthcheck() -> Dict[str, str]:  # pragma: no cover - trivial endpoint
        return {"status": "ok"}

    @app.get("/")
    async def dashboard() -> FileResponse:
        """Serve the dashboard HTML page."""
        dashboard_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.exists(dashboard_path):
            return FileResponse(dashboard_path)
        raise HTTPException(status_code=404, detail="Dashboard not found")

    return app


app = create_app()


