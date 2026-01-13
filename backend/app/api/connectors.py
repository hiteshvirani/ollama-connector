"""Connector CRUD API endpoints."""

import logging
from typing import List, Optional
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.connector import Connector
from ..models.usage import ConnectorUsage
from ..schemas.connector import (
    ConnectorCreate, 
    ConnectorUpdate, 
    ConnectorResponse, 
    ConnectorCreateResponse,
    ConnectorList,
    UsageStats
)
from ..middleware.auth import verify_admin_key
from ..services.auth import generate_api_key, hash_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connectors", tags=["Connectors"])


def generate_connector_id() -> str:
    """Generate a unique connector ID."""
    import secrets
    return f"conn_{secrets.token_hex(8)}"


@router.get("", response_model=ConnectorList)
async def list_connectors(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """List all connectors with pagination."""
    offset = (page - 1) * per_page
    
    # Build query
    query = select(Connector)
    count_query = select(func.count(Connector.id))
    
    if is_active is not None:
        query = query.where(Connector.is_active == is_active)
        count_query = count_query.where(Connector.is_active == is_active)
    
    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get items
    query = query.offset(offset).limit(per_page).order_by(Connector.created_at.desc())
    result = await db.execute(query)
    connectors = result.scalars().all()
    
    return ConnectorList(
        items=[ConnectorResponse.model_validate(c) for c in connectors],
        total=total,
        page=page,
        per_page=per_page
    )


@router.post("", response_model=ConnectorCreateResponse)
async def create_connector(
    data: ConnectorCreate,
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """Create a new connector with a generated API key."""
    # Generate ID and API key
    connector_id = generate_connector_id()
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    
    # Create connector
    connector = Connector(
        id=connector_id,
        api_key_hash=api_key_hash,
        name=data.name,
        description=data.description,
        allowed_models=data.allowed_models,
        blocked_models=data.blocked_models,
        priority=data.priority,
        routing_prefer=data.routing.prefer,
        routing_fallback=data.routing.fallback,
        routing_ollama_only=data.routing.ollama_only,
        routing_cloud_only=data.routing.cloud_only,
        rate_limit_per_minute=data.rate_limits.per_minute,
        rate_limit_per_hour=data.rate_limits.per_hour,
        burst_limit=data.rate_limits.burst,
        tokens_per_day=data.quotas.tokens_per_day,
        tokens_per_month=data.quotas.tokens_per_month,
        max_spend_per_day_usd=data.quotas.max_spend_per_day_usd,
        max_spend_per_month_usd=data.quotas.max_spend_per_month_usd,
        default_params=data.default_params.model_dump(exclude_none=True) if data.default_params else {},
        tags=data.tags,
        config_info=data.config_info,
    )
    
    db.add(connector)
    await db.commit()
    await db.refresh(connector)
    
    logger.info(f"Created connector: {connector_id} ({data.name})")
    
    return ConnectorCreateResponse(
        id=connector_id,
        api_key=api_key,  # Only returned once!
        name=data.name,
        created_at=connector.created_at
    )


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: str,
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """Get connector details."""
    result = await db.execute(
        select(Connector).where(Connector.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    return ConnectorResponse.model_validate(connector)


@router.patch("/{connector_id}", response_model=ConnectorResponse)
async def update_connector(
    connector_id: str,
    data: ConnectorUpdate,
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """Update connector settings."""
    result = await db.execute(
        select(Connector).where(Connector.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    
    # Handle nested objects
    if "routing" in update_data and update_data["routing"]:
        routing = update_data.pop("routing")
        connector.routing_prefer = routing.get("prefer", connector.routing_prefer)
        connector.routing_fallback = routing.get("fallback", connector.routing_fallback)
        connector.routing_ollama_only = routing.get("ollama_only", connector.routing_ollama_only)
        connector.routing_cloud_only = routing.get("cloud_only", connector.routing_cloud_only)
    
    if "rate_limits" in update_data and update_data["rate_limits"]:
        limits = update_data.pop("rate_limits")
        connector.rate_limit_per_minute = limits.get("per_minute", connector.rate_limit_per_minute)
        connector.rate_limit_per_hour = limits.get("per_hour", connector.rate_limit_per_hour)
        connector.burst_limit = limits.get("burst", connector.burst_limit)
    
    if "quotas" in update_data and update_data["quotas"]:
        quotas = update_data.pop("quotas")
        connector.tokens_per_day = quotas.get("tokens_per_day", connector.tokens_per_day)
        connector.tokens_per_month = quotas.get("tokens_per_month", connector.tokens_per_month)
        connector.max_spend_per_day_usd = quotas.get("max_spend_per_day_usd", connector.max_spend_per_day_usd)
        connector.max_spend_per_month_usd = quotas.get("max_spend_per_month_usd", connector.max_spend_per_month_usd)
    
    if "default_params" in update_data and update_data["default_params"]:
        connector.default_params = update_data.pop("default_params")
    
    # Apply remaining simple fields
    for key, value in update_data.items():
        if hasattr(connector, key):
            setattr(connector, key, value)
    
    await db.commit()
    await db.refresh(connector)
    
    logger.info(f"Updated connector: {connector_id}")
    
    return ConnectorResponse.model_validate(connector)


@router.delete("/{connector_id}")
async def delete_connector(
    connector_id: str,
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """Delete a connector."""
    result = await db.execute(
        select(Connector).where(Connector.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    await db.delete(connector)
    await db.commit()
    
    logger.info(f"Deleted connector: {connector_id}")
    
    return {"message": "Connector deleted", "id": connector_id}


@router.post("/{connector_id}/regenerate-key")
async def regenerate_api_key(
    connector_id: str,
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate the API key for a connector."""
    result = await db.execute(
        select(Connector).where(Connector.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Generate new key
    new_api_key = generate_api_key()
    connector.api_key_hash = hash_api_key(new_api_key)
    
    await db.commit()
    
    logger.info(f"Regenerated API key for connector: {connector_id}")
    
    return {
        "id": connector_id,
        "api_key": new_api_key,  # Only returned once!
        "message": "API key regenerated. Store this key securely."
    }


@router.get("/{connector_id}/usage", response_model=UsageStats)
async def get_connector_usage(
    connector_id: str,
    period: str = Query("day", regex="^(day|week|month)$"),
    _: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db)
):
    """Get usage statistics for a connector."""
    # Check connector exists
    result = await db.execute(
        select(Connector).where(Connector.id == connector_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Calculate date range
    today = date.today()
    if period == "day":
        start_date = today
    elif period == "week":
        start_date = today - timedelta(days=7)
    else:  # month
        start_date = today - timedelta(days=30)
    
    # Aggregate usage
    result = await db.execute(
        select(
            func.sum(ConnectorUsage.requests_total).label("requests_total"),
            func.sum(ConnectorUsage.requests_success).label("requests_success"),
            func.sum(ConnectorUsage.requests_failed).label("requests_failed"),
            func.sum(ConnectorUsage.tokens_input).label("tokens_input"),
            func.sum(ConnectorUsage.tokens_output).label("tokens_output"),
            func.sum(ConnectorUsage.tokens_total).label("tokens_total"),
            func.sum(ConnectorUsage.cost_usd).label("cost_usd"),
            func.avg(ConnectorUsage.avg_latency_ms).label("avg_latency_ms")
        ).where(
            ConnectorUsage.connector_id == connector_id,
            ConnectorUsage.date >= start_date
        )
    )
    row = result.first()
    
    return UsageStats(
        connector_id=connector_id,
        period=period,
        requests_total=row.requests_total or 0,
        requests_success=row.requests_success or 0,
        requests_failed=row.requests_failed or 0,
        tokens_input=row.tokens_input or 0,
        tokens_output=row.tokens_output or 0,
        tokens_total=row.tokens_total or 0,
        cost_usd=float(row.cost_usd or 0),
        avg_latency_ms=float(row.avg_latency_ms or 0)
    )
