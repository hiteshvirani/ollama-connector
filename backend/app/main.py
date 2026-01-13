"""FastAPI main application."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .config import get_settings

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Ollama Connector",
        description="Production-ready LLM Gateway with multi-provider support",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:7463",  # Admin panel
            "http://admin:3000",      # Docker internal
            "http://localhost:3000",  # Local dev
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(api_router)
    
    @app.get("/healthz")
    async def healthcheck():
        """Health check endpoint."""
        return {"status": "ok", "service": "ollama-connector"}
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "Ollama Connector",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/healthz"
        }
    
    @app.on_event("startup")
    async def on_startup():
        logger.info("🚀 Ollama Connector starting...")
        logger.info(f"📡 OpenRouter: {'configured' if settings.openrouter_api_key else 'not configured'}")
    
    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("👋 Ollama Connector shutting down...")
    
    return app


app = create_app()
