"""OpenAI-compatible chat completions API."""

import time
import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.connector import Connector
from ...models.usage import ConnectorUsage, RequestLog
from ...schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from ...middleware.auth import get_current_connector
from ...services.auth import is_model_allowed
from ...services.rate_limiter import check_rate_limit
from ...services.router import get_router, AllProvidersFailedError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    connector: Connector = Depends(get_current_connector),
    db: AsyncSession = Depends(get_db)
) -> ChatCompletionResponse:
    """
    OpenAI-compatible chat completions endpoint.
    
    Routes requests to Ollama nodes or OpenRouter based on connector settings.
    """
    start_time = time.time()
    
    # 1. Validate model access
    if not is_model_allowed(connector, request.model):
        raise HTTPException(
            status_code=403,
            detail=f"Model '{request.model}' is not allowed for this connector."
        )
    
    # 2. Check rate limits
    is_allowed, rate_info = await check_rate_limit(
        connector.id,
        connector.rate_limit_per_minute,
        connector.rate_limit_per_hour
    )
    
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "minute_remaining": rate_info["minute_remaining"],
                "hour_remaining": rate_info["hour_remaining"],
                "minute_reset": rate_info["minute_reset"],
                "hour_reset": rate_info["hour_reset"],
            }
        )
    
    # 3. Apply connector default params if not specified in request
    if connector.default_params:
        defaults = connector.default_params
        if request.temperature is None and defaults.get("temperature"):
            request.temperature = defaults["temperature"]
        if request.max_tokens is None and defaults.get("max_tokens"):
            request.max_tokens = defaults["max_tokens"]
    
    # 4. Route to provider
    try:
        llm_router = get_router()
        response = await llm_router.route(connector, request)
    except AllProvidersFailedError as e:
        # Log failure
        log_entry = RequestLog(
            connector_id=connector.id,
            model=request.model,
            status="error",
            error=str(e),
            latency_ms=int((time.time() - start_time) * 1000)
        )
        db.add(log_entry)
        await db.commit()
        
        raise HTTPException(
            status_code=503,
            detail={
                "error": "All providers failed",
                "message": str(e)
            }
        )
    
    # 5. Track usage
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Update daily usage
    today = date.today()
    usage_result = await db.execute(
        f"SELECT * FROM connector_usage WHERE connector_id = :cid AND date = :d",
        {"cid": connector.id, "d": today}
    )
    usage = usage_result.first()
    
    tokens_in = response.usage.prompt_tokens
    tokens_out = response.usage.completion_tokens
    
    if usage:
        await db.execute(
            """
            UPDATE connector_usage 
            SET requests_total = requests_total + 1,
                requests_success = requests_success + 1,
                tokens_input = tokens_input + :ti,
                tokens_output = tokens_output + :to,
                tokens_total = tokens_total + :tt
            WHERE connector_id = :cid AND date = :d
            """,
            {"cid": connector.id, "d": today, "ti": tokens_in, "to": tokens_out, "tt": tokens_in + tokens_out}
        )
    else:
        new_usage = ConnectorUsage(
            connector_id=connector.id,
            date=today,
            requests_total=1,
            requests_success=1,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            tokens_total=tokens_in + tokens_out
        )
        db.add(new_usage)
    
    # Log request
    log_entry = RequestLog(
        connector_id=connector.id,
        model=request.model,
        provider=response.provider,
        node_id=response.node_id,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        latency_ms=latency_ms,
        status="success"
    )
    db.add(log_entry)
    
    await db.commit()
    
    return response


@router.get("/models")
async def list_models(
    connector: Connector = Depends(get_current_connector)
):
    """
    List available models for this connector.
    """
    # TODO: Aggregate models from Ollama nodes + OpenRouter
    # For now, return allowed models from connector
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama-connector"
            }
            for model in (connector.allowed_models or ["*"])
        ]
    }
