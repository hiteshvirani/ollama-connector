"""FastAPI application acting as the Ollama orchestrator server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from collections import deque

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
class RequestLog:
    """Log entry for API requests."""
    timestamp: datetime
    request_ip: str
    endpoint: str
    method: str
    request_json: Optional[Dict[str, Any]] = None
    node_id: Optional[str] = None
    ip_version: Optional[str] = None  # "IPv4" or "IPv6"
    node_url: Optional[str] = None
    status_code: Optional[int] = None
    success: bool = False
    error: Optional[str] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "request_ip": self.request_ip,
            "endpoint": self.endpoint,
            "method": self.method,
            "request_json": self.request_json,
            "node_id": self.node_id,
            "ip_version": self.ip_version,
            "node_url": self.node_url,
            "status_code": self.status_code,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class NodeState:
    """Internal bookkeeping for a registered node."""

    record: NodeInfo
    active_jobs: int = 0
    failure_count: int = 0

    def bump_heartbeat(self, payload: HeartbeatPayload) -> None:
        # Get all fields from payload, including cloudflare_url
        payload_data = payload.model_dump(exclude_none=False)
        # Create new NodeInfo with all fields to ensure cloudflare_url is included
        self.record = NodeInfo(
            **payload_data,
            last_seen=datetime.now(timezone.utc),
            status="online"
        )
        self.failure_count = 0

    def to_dict(self) -> Dict[str, object]:
        data = self.record.model_dump(exclude_none=False)
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
    # Request logs: keep last 1000 entries (FIFO)
    app.state.request_logs: deque = deque(maxlen=1000)
    app.state.logs_lock = asyncio.Lock()

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

    def build_node_url(node: NodeInfo, connection_type: str) -> str:
        """
        Build the URL for a node based on connection type.
        
        Args:
            node: NodeInfo object containing connection details
            connection_type: One of "cloudflare", "ipv4", or "ipv6"
        
        Returns:
            Full URL to the node's execute endpoint
        """
        if connection_type == "cloudflare":
            if not node.cloudflare_url:
                raise ValueError("Node has no Cloudflare URL")
            # Cloudflare URL should already be a full URL, just append /execute if needed
            base_url = node.cloudflare_url.rstrip('/')
            if not base_url.startswith('http'):
                base_url = f"http://{base_url}"
            return f"{base_url}/execute"
        elif connection_type == "ipv4":
            if not node.ipv4:
                raise ValueError("Node has no IPv4 address")
            host = node.ipv4
            return f"http://{host}:{node.port}/execute"
        elif connection_type == "ipv6":
            if not node.ipv6:
                raise ValueError("Node has no IPv6 address")
            host = node.ipv6
            # Format IPv6 addresses properly
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            return f"http://{host}:{node.port}/execute"
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")

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
        
        def get_cpu_load(item):
            """Extract CPU load value, handling both dict and object cases."""
            load = item[1].record.load
            if not load:
                return 1.0
            # Handle both dict and LoadInfo object
            if isinstance(load, dict):
                return load.get("cpu", 1.0) if load.get("cpu") is not None else 1.0
            else:
                return load.cpu if load.cpu is not None else 1.0
        
        candidates.sort(
            key=lambda item: (
                item[1].active_jobs,
                get_cpu_load(item),
                item[1].failure_count,
            )
        )
        return [node_id for node_id, _ in candidates]

    async def snapshot_node(node_id: str) -> Optional[NodeInfo]:
        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if not entry:
                return None
            snapshot = entry.record.copy(deep=True)
            # Ensure cloudflare_url is preserved
            if hasattr(entry.record, 'cloudflare_url'):
                snapshot.cloudflare_url = entry.record.cloudflare_url
            return snapshot

    async def dispatch_to_node(node_id: str, payload: JobDispatchPayload, log_entry: Optional[RequestLog] = None) -> Response:
        http = app.state.http
        if http is None:  # pragma: no cover - startup invariant
            raise RuntimeError("HTTP client not initialised")

        node_snapshot = await snapshot_node(node_id)
        if not node_snapshot:
            raise NodeDispatchError(node_id, "Node disappeared before dispatch", status_code=410)

        # CRITICAL: Build connection strategies FRESH for EVERY request
        # Priority order MUST be: Cloudflare -> IPv4 -> IPv6
        # This ensures Cloudflare is tried FIRST for every single request
        
        # Get Cloudflare URL from snapshot
        cf_url = getattr(node_snapshot, 'cloudflare_url', None)
        
        # Log what we have in the snapshot for debugging
        LOGGER.info("🔍 [REQUEST START] Node %s snapshot: cloudflare_url=%s (type: %s), ipv4=%s, ipv6=%s", 
                   node_id, cf_url, type(cf_url).__name__ if cf_url else 'None', node_snapshot.ipv4, node_snapshot.ipv6)

        # Build connection strategies list FRESH - Cloudflare ALWAYS first if available
        connection_strategies = []
        
        # 1. CLOUDFLARE - MUST BE FIRST if available
        if cf_url and isinstance(cf_url, str) and cf_url.strip():
            connection_strategies.append("cloudflare")
            LOGGER.info("✅ [PRIORITY 1] Node %s will try CLOUDFLARE FIRST: %s", node_id, cf_url)
        else:
            LOGGER.warning("⚠️  Node %s has NO valid Cloudflare URL (value: %s, type: %s) - skipping Cloudflare", 
                         node_id, repr(cf_url), type(cf_url).__name__ if cf_url else 'None')
        
        # 2. IPv4 - Second priority
        if node_snapshot.ipv4:
            connection_strategies.append("ipv4")
            LOGGER.info("✅ [PRIORITY 2] Node %s will try IPv4: %s", node_id, node_snapshot.ipv4)
        
        # 3. IPv6 - Last priority
        if node_snapshot.ipv6:
            connection_strategies.append("ipv6")
            LOGGER.info("✅ [PRIORITY 3] Node %s will try IPv6: %s", node_id, node_snapshot.ipv6)
        
        LOGGER.info("🎯 [STRATEGY ORDER] Node %s connection strategies (FRESH for this request): %s", node_id, connection_strategies)
        
        if not connection_strategies:
            raise NodeDispatchError(node_id, "Node has no reachable address (no Cloudflare URL, IPv4, or IPv6)", status_code=503)

        last_error = None
        for idx, connection_type in enumerate(connection_strategies, 1):
            try:
                target_url = build_node_url(node_snapshot, connection_type)
                LOGGER.info("🚀 [ATTEMPT %d/%d] Dispatching job %s to node %s via %s (%s)", 
                           idx, len(connection_strategies), payload.job_id, node_id, connection_type.upper(), target_url)

                # Update log entry with node info
                if log_entry:
                    log_entry.node_id = node_id
                    log_entry.ip_version = connection_type.upper()
                    log_entry.node_url = target_url

                await mark_job_start(node_id)
                start_time = datetime.now(timezone.utc)
                try:
                    response = await http.post(target_url, json=payload.model_dump())
                except Exception as exc:  # noqa: BLE001
                    await mark_job_end(node_id, success=False)
                    last_error = exc
                    if log_entry:
                        log_entry.error = str(exc)
                        log_entry.duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    LOGGER.warning("❌ [ATTEMPT %d/%d] Failed to connect via %s (%s): %s - trying next strategy", 
                                 idx, len(connection_strategies), connection_type, target_url, exc)
                    # Try next connection strategy
                    continue

                duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                success = 200 <= response.status_code < 300
                await mark_job_end(node_id, success=success)

                if log_entry:
                    log_entry.status_code = response.status_code
                    log_entry.success = success
                    log_entry.duration_ms = duration_ms
                    if not success:
                        log_entry.error = response.text or response.reason_phrase

                if not success:
                    message = response.text or response.reason_phrase
                    last_error = Exception(f"HTTP {response.status_code}: {message}")
                    LOGGER.warning("❌ [ATTEMPT %d/%d] HTTP error via %s (%s): %s - trying next strategy", 
                                 idx, len(connection_strategies), connection_type, target_url, message)
                    continue

                # Success!
                LOGGER.info("✅ [SUCCESS] Job %s completed via %s (%s) in %.2fms", 
                           payload.job_id, connection_type.upper(), target_url, duration_ms)
                media_type = response.headers.get("content-type", "application/json")
                return Response(content=response.content, media_type=media_type, status_code=response.status_code)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if log_entry:
                    log_entry.error = str(exc)
                continue

        # All strategies failed
        error_msg = str(last_error) if last_error else "All connection strategies failed"
        raise NodeDispatchError(node_id, f"Request failed: {error_msg}", status_code=503)

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
        """
        Register or update a node's heartbeat.
        
        Network handling strategy:
        - The connection IP (request.client.host) is the IP the server can reach
        - This is stored as the primary IP (overwrites client's detected IP)
        - Client's detected IPs are kept for reference but connection IP takes priority
        - This handles NAT, different networks, and cross-network scenarios
        """
        # Get the reachable address from the connection (most reliable)
        # This is the IP the server can actually connect back to
        connection_ip = request.client.host if request.client else None

        payload_data = payload.model_dump()
        node_id = payload.node_id

        # Store the connection IP as the primary reachable address
        # This works for any network configuration:
        # - Same network: connection IP is the direct IP
        # - Different networks: connection IP is the public/NAT IP
        # - NAT scenarios: connection IP is the externally reachable IP
        # - IPv6: connection IP is the IPv6 address
        if connection_ip:
            if ":" not in connection_ip:
                # IPv4 connection - use as primary IPv4
                payload_data["ipv4"] = connection_ip
                LOGGER.debug("Node %s connection IPv4: %s (client reported: %s)", 
                           node_id, connection_ip, payload_data.get("ipv4"))
            else:
                # IPv6 connection - use as primary IPv6
                payload_data["ipv6"] = connection_ip
                LOGGER.debug("Node %s connection IPv6: %s (client reported: %s)", 
                           node_id, connection_ip, payload_data.get("ipv6"))

        payload = HeartbeatPayload(**payload_data)

        async with app.state.registry_lock:
            entry = app.state.registry.get(node_id)
            if entry:
                entry.bump_heartbeat(payload)
                LOGGER.debug("Updated heartbeat for node %s (Cloudflare: %s, IPv4: %s, IPv6: %s)", 
                           node_id, payload.cloudflare_url, payload.ipv4, payload.ipv6)
            else:
                record = NodeInfo(**payload.model_dump(exclude_none=False), last_seen=datetime.now(timezone.utc), status="online")
                app.state.registry[node_id] = NodeState(record=record)
                LOGGER.info("Registered new node %s (Cloudflare: %s, IPv4: %s, IPv6: %s, connection: %s)", 
                          node_id, payload.cloudflare_url, payload.ipv4, payload.ipv6, connection_ip)

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
    async def create_job(request_payload: JobRequest, request: Request) -> Response:
        # Create log entry for this request
        request_ip = request.client.host if request.client else "unknown"
        log_entry = RequestLog(
            timestamp=datetime.now(timezone.utc),
            request_ip=request_ip,
            endpoint="/jobs",
            method="POST",
            request_json=request_payload.model_dump(),
        )

        candidate_ids = await choose_node_ids(request_payload.model)
        if not candidate_ids:
            log_entry.error = "No healthy nodes available for requested model"
            log_entry.status_code = 503
            async with app.state.logs_lock:
                app.state.request_logs.append(log_entry)
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
                response = await dispatch_to_node(node_id, dispatch_payload, log_entry=log_entry)
                # Log successful request
                async with app.state.logs_lock:
                    app.state.request_logs.append(log_entry)
                return response
            except NodeDispatchError as exc:
                LOGGER.warning("Node %s failed job %s: %s", exc.node_id, job_id, exc)
                errors.append({"node_id": exc.node_id, "message": str(exc), "status": exc.status_code})
                # Update log entry with error but continue to next node
                if not log_entry.error:
                    log_entry.error = f"Node {exc.node_id}: {exc}"
                continue

        # All nodes failed
        log_entry.error = f"All candidate nodes failed: {errors}"
        log_entry.status_code = 503
        async with app.state.logs_lock:
            app.state.request_logs.append(log_entry)
        
        detail = {
            "message": "All candidate nodes failed to execute the job",
            "errors": errors,
            "job_id": job_id,
        }
        raise HTTPException(status_code=503, detail=detail)

    @app.get("/logs")
    async def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
        """Get request logs for debugging and monitoring."""
        async with app.state.logs_lock:
            # Return most recent logs (deque is already in order)
            logs = list(app.state.request_logs)[-limit:]
            return [log.to_dict() for log in reversed(logs)]  # Most recent first

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


