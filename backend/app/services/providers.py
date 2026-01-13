"""Unified LLM Provider that works with any OpenAI-compatible endpoint."""

import time
import logging
from typing import Optional, Dict, Any
import httpx

from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChoice, ChatMessage, UsageInfo
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class UnifiedLLMProvider:
    """
    A single provider class that works with any OpenAI-compatible endpoint.
    Works with: Ollama, OpenRouter, OpenAI, Azure OpenAI, etc.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str = "unused",
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 120.0,
        name: str = "unknown"
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = headers or {}
        self.timeout = timeout
        self.name = name
    
    async def chat_completion(
        self,
        request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Send chat completion request."""
        start_time = time.time()
        
        # Build request payload
        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": request.stream,
        }
        
        # Add optional parameters
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop is not None:
            payload["stop"] = request.stop
        
        # Add Ollama-specific options if present
        if request.options:
            payload["options"] = request.options
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
        
        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[{self.name}] Chat completion for {request.model} completed in {latency_ms}ms")
        
        # Parse response to our schema
        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            created=data.get("created", int(time.time())),
            model=data.get("model", request.model),
            choices=[
                ChatCompletionChoice(
                    index=c.get("index", 0),
                    message=ChatMessage(
                        role=c["message"]["role"],
                        content=c["message"]["content"]
                    ),
                    finish_reason=c.get("finish_reason", "stop")
                )
                for c in data.get("choices", [])
            ],
            usage=UsageInfo(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0)
            ),
            provider=self.name
        )
    
    async def list_models(self) -> list:
        """List available models from this provider."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to list models: {e}")
            return []


# ===== Pre-configured providers =====

def get_openrouter_provider() -> Optional[UnifiedLLMProvider]:
    """Get OpenRouter provider if configured."""
    if not settings.openrouter_api_key:
        return None
    
    return UnifiedLLMProvider(
        base_url="https://openrouter.ai/api",
        api_key=settings.openrouter_api_key,
        headers={
            "HTTP-Referer": settings.openrouter_site_url or "https://ollama-connector.local",
            "X-Title": settings.openrouter_site_name or "Ollama Connector"
        },
        timeout=settings.openrouter_request_timeout,
        name="openrouter"
    )


def get_ollama_provider(base_url: str) -> UnifiedLLMProvider:
    """Get Ollama provider for a specific node."""
    return UnifiedLLMProvider(
        base_url=base_url,
        api_key="ollama",  # Placeholder, not used by Ollama
        timeout=settings.ollama_request_timeout,
        name="ollama"
    )
