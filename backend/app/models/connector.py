"""Connector SQLAlchemy model."""

from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, BigInteger, Boolean, Float, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from ..database import Base


class Connector(Base):
    """
    Connector model representing an API credential with access controls,
    rate limits, quotas, and routing preferences.
    """
    __tablename__ = "connectors"
    
    # Identity
    id = Column(String(50), primary_key=True)
    api_key_hash = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Access control
    allowed_models = Column(JSONB, default=["*"])
    blocked_models = Column(JSONB, default=[])
    
    # Priority (1-10, higher = more priority)
    priority = Column(Integer, default=5)
    
    # Routing preferences
    routing_prefer = Column(String(50), default="ollama")
    routing_fallback = Column(String(50), default="openrouter")
    routing_ollama_only = Column(Boolean, default=False)
    routing_cloud_only = Column(Boolean, default=False)
    
    # Rate limits
    rate_limit_per_minute = Column(Integer, default=60)
    rate_limit_per_hour = Column(Integer, default=1000)
    burst_limit = Column(Integer, default=20)
    
    # Quotas
    tokens_per_day = Column(BigInteger, nullable=True)
    tokens_per_month = Column(BigInteger, nullable=True)
    max_spend_per_day_usd = Column(Float, nullable=True)
    max_spend_per_month_usd = Column(Float, nullable=True)
    
    # Default parameters
    default_params = Column(JSONB, default={})
    
    # Metadata
    tags = Column(JSONB, default=[])
    config_info = Column(JSONB, default={})
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<Connector {self.id}: {self.name}>"
