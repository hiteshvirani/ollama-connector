"""Node management API endpoints."""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field

from ..middleware.auth import verify_admin_key
from ..services.rate_limiter import get_redis
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/nodes", tags=["Nodes"])


class LoadInfo(BaseModel):
    """Node load information."""
    cpu: Optional[float] = None
    memory: Optional[float] = None


class HeartbeatPayload(BaseModel):
    """Payload sent by Ollama nodes."""
    node_id: str = Field(..., description="Unique node identifier")
    cloudflare_url: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    port: int = Field(default=11434)
    models: List[str] = Field(default=[])
    load: Optional[LoadInfo] = None
    metadata: dict = Field(default={})


class NodeInfo(BaseModel):
    """Node information returned to clients."""
    node_id: str
    cloudflare_url: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    port: int
    models: List[str]
    load: Optional[LoadInfo] = None
    status: str
    last_seen: str
    active_jobs: int = 0
    failure_count: int = 0


@router.post("/heartbeat")
async def register_heartbeat(
    payload: HeartbeatPayload,
    request: Request,
    x_node_secret: Optional[str] = Header(None, alias="X-Node-Secret")
):
    """
    Register or update a node's heartbeat.
    Called periodically by Ollama node agents.
    """
    # Validate node secret
    if x_node_secret != settings.node_secret:
        raise HTTPException(status_code=403, detail="Invalid node secret")
    
    r = await get_redis()
    node_key = f"node:{payload.node_id}"
    
    # Get connection IP as fallback
    connection_ip = request.client.host if request.client else None
    
    # Build node data
    node_data = {
        "node_id": payload.node_id,
        "cloudflare_url": payload.cloudflare_url or "",
        "ipv4": payload.ipv4 or connection_ip or "",
        "ipv6": payload.ipv6 or "",
        "port": str(payload.port),
        "models": json.dumps(payload.models),
        "cpu_load": str(payload.load.cpu if payload.load else 0.0),
        "memory_load": str(payload.load.memory if payload.load else 0.0),
        "status": "online",
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "active_jobs": "0",
        "failure_count": "0",
        "metadata": json.dumps(payload.metadata)
    }
    
    # Store in Redis with TTL
    await r.hset(node_key, mapping=node_data)
    await r.expire(node_key, 90)  # 90 second TTL
    
    logger.info(f"Heartbeat from node {payload.node_id}: {len(payload.models)} models")
    
    return {"status": "ok", "node_id": payload.node_id}


@router.get("", response_model=List[NodeInfo])
async def list_nodes(
    _: bool = Depends(verify_admin_key)
):
    """List all registered nodes."""
    r = await get_redis()
    
    node_keys = await r.keys("node:*")
    nodes = []
    
    for key in node_keys:
        data = await r.hgetall(key)
        if not data:
            continue
        
        # Parse models JSON
        models = []
        if data.get("models"):
            try:
                models = json.loads(data["models"])
            except:
                pass
        
        nodes.append(NodeInfo(
            node_id=data.get("node_id", key.replace("node:", "")),
            cloudflare_url=data.get("cloudflare_url") or None,
            ipv4=data.get("ipv4") or None,
            ipv6=data.get("ipv6") or None,
            port=int(data.get("port", 11434)),
            models=models,
            load=LoadInfo(
                cpu=float(data.get("cpu_load", 0)),
                memory=float(data.get("memory_load", 0))
            ),
            status=data.get("status", "unknown"),
            last_seen=data.get("last_seen", ""),
            active_jobs=int(data.get("active_jobs", 0)),
            failure_count=int(data.get("failure_count", 0))
        ))
    
    return nodes


@router.delete("/{node_id}")
async def remove_node(
    node_id: str,
    _: bool = Depends(verify_admin_key)
):
    """Remove a node from the registry."""
    r = await get_redis()
    node_key = f"node:{node_id}"
    
    deleted = await r.delete(node_key)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")
    
    logger.info(f"Removed node: {node_id}")
    
    return {"message": "Node removed", "node_id": node_id}
