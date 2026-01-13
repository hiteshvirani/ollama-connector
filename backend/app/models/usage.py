"""Usage tracking SQLAlchemy model."""

from datetime import datetime, date
from sqlalchemy import Column, String, Integer, BigInteger, Float, Date, DateTime, ForeignKey, UniqueConstraint
from ..database import Base


class ConnectorUsage(Base):
    """
    Daily usage tracking for each connector.
    One row per connector per day.
    """
    __tablename__ = "connector_usage"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    connector_id = Column(String(50), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    
    # Request counts
    requests_total = Column(Integer, default=0)
    requests_success = Column(Integer, default=0)
    requests_failed = Column(Integer, default=0)
    
    # Token usage
    tokens_input = Column(BigInteger, default=0)
    tokens_output = Column(BigInteger, default=0)
    tokens_total = Column(BigInteger, default=0)
    
    # Cost tracking
    cost_usd = Column(Float, default=0.0)
    
    # Latency stats
    avg_latency_ms = Column(Float, default=0.0)
    
    __table_args__ = (
        UniqueConstraint('connector_id', 'date', name='uix_connector_date'),
    )
    
    def __repr__(self) -> str:
        return f"<ConnectorUsage {self.connector_id} on {self.date}>"


class RequestLog(Base):
    """
    Individual request logs for debugging and analytics.
    """
    __tablename__ = "request_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    connector_id = Column(String(50), ForeignKey("connectors.id", ondelete="SET NULL"), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Request info
    model = Column(String(100))
    provider = Column(String(50))  # 'ollama', 'openrouter', etc.
    node_id = Column(String(100))  # Which Ollama node was used
    
    # Token usage
    tokens_input = Column(Integer)
    tokens_output = Column(Integer)
    
    # Performance
    latency_ms = Column(Integer)
    
    # Status
    status = Column(String(20))  # 'success', 'error', 'rate_limited', etc.
    error = Column(String)
    
    def __repr__(self) -> str:
        return f"<RequestLog {self.id} for {self.connector_id}>"
