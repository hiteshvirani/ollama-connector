"""Authentication service for API key validation."""

import hashlib
import secrets
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.connector import Connector


def generate_api_key(prefix: str = "sk-conn") -> str:
    """Generate a new API key."""
    random_part = secrets.token_hex(24)
    return f"{prefix}-{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def get_connector_by_api_key(
    db: AsyncSession,
    api_key: str
) -> Optional[Connector]:
    """
    Look up a connector by its API key.
    Returns None if not found or inactive.
    """
    api_key_hash = hash_api_key(api_key)
    
    result = await db.execute(
        select(Connector).where(
            Connector.api_key_hash == api_key_hash,
            Connector.is_active == True
        )
    )
    return result.scalar_one_or_none()


def is_model_allowed(connector: Connector, model: str) -> bool:
    """
    Check if a model is allowed for this connector.
    
    Rules:
    - blocked_models takes precedence
    - allowed_models can be ["*"] for all models
    - Otherwise, model must be in allowed_models list
    """
    # Check blocked first
    if connector.blocked_models:
        if model in connector.blocked_models:
            return False
    
    # Check allowed
    allowed = connector.allowed_models or ["*"]
    if "*" in allowed:
        return True
    
    return model in allowed
