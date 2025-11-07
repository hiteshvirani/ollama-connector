"""Shared Pydantic schemas for the Ollama connector project."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoadInfo(BaseModel):
    """Describes resource utilisation metrics reported by an Ollama node."""

    cpu: Optional[float] = Field(
        default=None, description="CPU utilisation ratio between 0.0 and 1.0."
    )
    memory: Optional[float] = Field(
        default=None, description="Memory utilisation ratio between 0.0 and 1.0."
    )


class HeartbeatPayload(BaseModel):
    """Payload sent from a node to the server on every heartbeat."""

    node_id: str = Field(..., description="Stable identifier for the node.")
    ipv4: Optional[str] = Field(
        default=None,
        description="Externally reachable IPv4 address for the node API, if available.",
    )
    ipv6: Optional[str] = Field(
        default=None,
        description="Externally reachable IPv6 address for the node API, if available.",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="TCP port where the node agent listens for job execution requests.",
    )
    models: List[str] = Field(
        default_factory=list,
        description="List of Ollama model identifiers currently available on the node.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key/value metadata provided by the node."
    )
    load: Optional[LoadInfo] = Field(
        default=None,
        description="Optional load information used for scheduling decisions.",
    )


class NodeInfo(HeartbeatPayload):
    """Extends the heartbeat payload with server-side bookkeeping fields."""

    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of the latest heartbeat."
    )
    status: str = Field(
        default="online",
        description="Computed status for the node (e.g. online, offline, degraded).",
    )


class JobRequest(BaseModel):
    """Represents an incoming request to run a prompt on any available node."""

    model: str = Field(..., description="Desired Ollama model identifier.")
    prompt: str = Field(..., description="Prompt text to send to the model.")
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional model execution parameters passed through to Ollama.",
    )
    stream: bool = Field(
        default=True,
        description="Whether the caller expects a streamed response from Ollama.",
    )


class JobDispatchPayload(BaseModel):
    """Payload sent from the server to a node when dispatching a job."""

    job_id: str = Field(..., description="Unique identifier assigned by the server.")
    model: str = Field(..., description="Model to execute on the node.")
    prompt: str = Field(..., description="Prompt text to run against the model.")
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional options forwarded to Ollama.",
    )
    stream: bool = Field(
        default=True,
        description="Whether the node should stream results back to the server.",
    )


class JobStatus(BaseModel):
    """Represents the current status of a dispatched job."""

    job_id: str
    node_id: str
    status: str
    error: Optional[str] = None

