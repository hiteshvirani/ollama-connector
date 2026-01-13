"""Authentication middleware for API key validation."""

from typing import Optional
from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.connector import Connector
from ..services.auth import get_connector_by_api_key
from ..config import get_settings

settings = get_settings()

# API Key header
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def extract_bearer_token(auth_header: Optional[str]) -> Optional[str]:
    """Extract token from 'Bearer <token>' header."""
    if not auth_header:
        return None
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return auth_header


async def get_current_connector(
    auth_header: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Connector:
    """
    Dependency that validates API key and returns the associated connector.
    Raises 401 if no key, 403 if invalid/inactive.
    """
    api_key = extract_bearer_token(auth_header)
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Use 'Authorization: Bearer <api_key>' header."
        )
    
    connector = await get_connector_by_api_key(db, api_key)
    
    if not connector:
        raise HTTPException(
            status_code=403,
            detail="Invalid or inactive API key."
        )
    
    return connector


async def get_optional_connector(
    auth_header: Optional[str] = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> Optional[Connector]:
    """
    Dependency that returns connector if valid API key, None otherwise.
    Used for endpoints that can work with or without auth.
    """
    api_key = extract_bearer_token(auth_header)
    
    if not api_key:
        return None
    
    return await get_connector_by_api_key(db, api_key)


async def verify_admin_key(
    admin_key: Optional[str] = Security(admin_key_header)
) -> bool:
    """
    Dependency that validates admin API key.
    Used for connector management endpoints.
    """
    if not admin_key:
        raise HTTPException(
            status_code=401,
            detail="Admin API key required. Use 'X-Admin-Key' header."
        )
    
    if admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin API key."
        )
    
    return True
