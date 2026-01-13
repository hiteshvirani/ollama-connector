"""Smart router for directing requests to the best provider."""

import logging
from typing import Optional, List, Dict, Any
import redis.asyncio as redis

from ..models.connector import Connector
from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from .providers import get_ollama_provider, get_openrouter_provider, UnifiedLLMProvider
from .rate_limiter import get_redis
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class NoHealthyNodesError(Exception):
    """Raised when no healthy Ollama nodes are available."""
    pass


class AllProvidersFailedError(Exception):
    """Raised when all providers fail to handle a request."""
    pass


class SmartRouter:
    """
    Routes requests based on connector preferences and system state.
    Priority: Ollama (local) → OpenRouter (cloud)
    """
    
    def __init__(self):
        self.openrouter = get_openrouter_provider()
    
    async def route(
        self,
        connector: Connector,
        request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """
        Route a request to the best available provider.
        """
        # Get provider order based on connector preferences
        providers = self._get_provider_order(connector)
        
        errors = []
        for provider_type in providers:
            try:
                if provider_type == "ollama":
                    # Try to get a healthy Ollama node
                    node = await self._get_best_ollama_node(
                        request.model,
                        connector.priority
                    )
                    if node:
                        provider = get_ollama_provider(node["url"])
                        response = await provider.chat_completion(request)
                        response.node_id = node["node_id"]
                        return response
                    else:
                        logger.info(f"No Ollama nodes available for {request.model}")
                        continue
                
                elif provider_type == "openrouter" and self.openrouter:
                    response = await self.openrouter.chat_completion(request)
                    return response
                
                elif provider_type == "openrouter:free" and self.openrouter:
                    # Only use free models on OpenRouter
                    if self._is_free_model(request.model):
                        response = await self.openrouter.chat_completion(request)
                        return response
                    else:
                        logger.info(f"Model {request.model} is not free, skipping openrouter:free")
                        continue
                        
            except Exception as e:
                logger.warning(f"Provider {provider_type} failed: {e}")
                errors.append({"provider": provider_type, "error": str(e)})
                continue
        
        # All providers failed
        raise AllProvidersFailedError(f"All providers failed: {errors}")
    
    def _get_provider_order(self, connector: Connector) -> List[str]:
        """Get ordered list of providers to try."""
        order = []
        
        # Check routing constraints
        if connector.routing_ollama_only:
            return ["ollama"]
        if connector.routing_cloud_only:
            if connector.routing_prefer in ["openrouter", "openrouter:free"]:
                return [connector.routing_prefer]
            return ["openrouter"]
        
        # Add preferred provider first
        prefer = connector.routing_prefer or "ollama"
        order.append(prefer)
        
        # Add fallback if different
        fallback = connector.routing_fallback
        if fallback and fallback != prefer:
            order.append(fallback)
        
        return order
    
    async def _get_best_ollama_node(
        self,
        model: str,
        priority: int
    ) -> Optional[Dict[str, Any]]:
        """
        Select the best available Ollama node for a model.
        Considers:
        - Model availability
        - Current load
        - Failure count
        - Request priority
        """
        r = await get_redis()
        
        # Get all active nodes from Redis
        node_keys = await r.keys("node:*")
        if not node_keys:
            return None
        
        candidates = []
        for key in node_keys:
            node_data = await r.hgetall(key)
            if not node_data:
                continue
            
            # Check if node has the requested model
            models = node_data.get("models", "[]")
            if isinstance(models, str):
                import json
                try:
                    models = json.loads(models)
                except:
                    models = []
            
            # Check model availability
            if model not in models and "*" not in models:
                continue
            
            # Check node status
            status = node_data.get("status", "offline")
            if status != "online":
                continue
            
            # Build node info
            node_id = node_data.get("node_id", key.replace("node:", ""))
            candidates.append({
                "node_id": node_id,
                "url": self._build_node_url(node_data),
                "active_jobs": int(node_data.get("active_jobs", 0)),
                "cpu_load": float(node_data.get("cpu_load", 0.5)),
                "failure_count": int(node_data.get("failure_count", 0)),
            })
        
        if not candidates:
            return None
        
        # Sort by: active_jobs (adjusted by priority), cpu_load, failure_count
        candidates.sort(key=lambda n: (
            n["active_jobs"] - (priority * 0.1),  # Higher priority = lower apparent load
            n["cpu_load"],
            n["failure_count"]
        ))
        
        return candidates[0]
    
    def _build_node_url(self, node_data: Dict[str, Any]) -> str:
        """Build the URL for an Ollama node."""
        # Try Cloudflare URL first
        cf_url = node_data.get("cloudflare_url")
        if cf_url:
            return cf_url.rstrip("/")
        
        # Try IPv4
        ipv4 = node_data.get("ipv4")
        port = node_data.get("port", "11434")
        if ipv4:
            return f"http://{ipv4}:{port}"
        
        # Try IPv6
        ipv6 = node_data.get("ipv6")
        if ipv6:
            if ":" in ipv6 and not ipv6.startswith("["):
                ipv6 = f"[{ipv6}]"
            return f"http://{ipv6}:{port}"
        
        # Default to localhost (shouldn't happen)
        return f"http://localhost:{port}"
    
    def _is_free_model(self, model: str) -> bool:
        """Check if a model is free on OpenRouter."""
        free_patterns = [":free", "/free", "free:"]
        return any(p in model.lower() for p in free_patterns)


# Global router instance
_router: Optional[SmartRouter] = None


def get_router() -> SmartRouter:
    """Get the global router instance."""
    global _router
    if _router is None:
        _router = SmartRouter()
    return _router
