"""Pydantic schemas for Connector API."""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class RoutingPreference(BaseModel):
    """Routing configuration."""
    prefer: Literal["ollama", "openrouter", "openrouter:free"] = "ollama"
    fallback: Optional[Literal["ollama", "openrouter", "openrouter:free"]] = "openrouter"
    ollama_only: bool = False
    cloud_only: bool = False


class RateLimits(BaseModel):
    """Rate limiting configuration."""
    per_minute: int = Field(default=60, ge=1)
    per_hour: int = Field(default=1000, ge=1)
    burst: int = Field(default=20, ge=1)


class Quotas(BaseModel):
    """Usage quota configuration."""
    tokens_per_day: Optional[int] = None
    tokens_per_month: Optional[int] = None
    max_spend_per_day_usd: Optional[float] = None
    max_spend_per_month_usd: Optional[float] = None


class DefaultParams(BaseModel):
    """Default parameters for requests."""
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    system_prompt: Optional[str] = None


# ===== Request Schemas =====

class ConnectorCreate(BaseModel):
    """Schema for creating a new connector."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    allowed_models: List[str] = Field(default=["*"])
    blocked_models: List[str] = Field(default=[])
    priority: int = Field(default=5, ge=1, le=10)
    routing: RoutingPreference = Field(default_factory=RoutingPreference)
    rate_limits: RateLimits = Field(default_factory=RateLimits)
    quotas: Quotas = Field(default_factory=Quotas)
    default_params: DefaultParams = Field(default_factory=DefaultParams)
    tags: List[str] = Field(default=[])
    config_info: Dict[str, Any] = Field(default={})


class ConnectorUpdate(BaseModel):
    """Schema for updating a connector."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    allowed_models: Optional[List[str]] = None
    blocked_models: Optional[List[str]] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    routing: Optional[RoutingPreference] = None
    rate_limits: Optional[RateLimits] = None
    quotas: Optional[Quotas] = None
    default_params: Optional[DefaultParams] = None
    tags: Optional[List[str]] = None
    config_info: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


# ===== Response Schemas =====

class ConnectorResponse(BaseModel):
    """Schema for connector in responses."""
    id: str
    name: str
    description: Optional[str] = None
    allowed_models: List[str]
    blocked_models: List[str]
    priority: int
    routing_prefer: str
    routing_fallback: Optional[str]
    routing_ollama_only: bool
    routing_cloud_only: bool
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    burst_limit: int
    tokens_per_day: Optional[int] = None
    tokens_per_month: Optional[int] = None
    max_spend_per_day_usd: Optional[float] = None
    max_spend_per_month_usd: Optional[float] = None
    default_params: Dict[str, Any]
    tags: List[str]
    config_info: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ConnectorCreateResponse(BaseModel):
    """Response when creating a new connector, includes API key."""
    id: str
    api_key: str  # Only shown once at creation
    name: str
    created_at: datetime


class ConnectorList(BaseModel):
    """Paginated list of connectors."""
    items: List[ConnectorResponse]
    total: int
    page: int
    per_page: int


class UsageStats(BaseModel):
    """Usage statistics for a connector."""
    connector_id: str
    period: str  # "day", "week", "month"
    requests_total: int
    requests_success: int
    requests_failed: int
    tokens_input: int
    tokens_output: int
    tokens_total: int
    cost_usd: float
    avg_latency_ms: float
