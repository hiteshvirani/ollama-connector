"""API package."""

from fastapi import APIRouter
from .v1 import router as v1_router
from .connectors import router as connectors_router
from .nodes import router as nodes_router

router = APIRouter()

# Include all API routers
router.include_router(v1_router)  # /v1/chat/completions, /v1/models
router.include_router(connectors_router, prefix="/api")  # /api/connectors
router.include_router(nodes_router, prefix="/api")  # /api/nodes
