"""Configuration settings for the backend."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "postgresql+asyncpg://ollama:ollama_secret_2026@postgres:5432/ollama_connector"
    
    # Redis
    redis_url: str = "redis://redis:6379/0"
    
    # Security
    admin_api_key: str = "admin-sk-default"
    node_secret: str = "node-secret-default"
    
    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_site_url: str = ""
    openrouter_site_name: str = "Ollama Connector"
    
    # Logging
    log_level: str = "INFO"
    
    # Rate limiting defaults
    default_rate_limit_per_minute: int = 60
    default_rate_limit_per_hour: int = 1000
    default_tokens_per_day: int = 1000000
    
    # Timeouts
    ollama_request_timeout: float = 120.0
    openrouter_request_timeout: float = 60.0
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
