"""OpenAI-compatible chat completion schemas."""

from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat message."""
    role: Literal["system", "user", "assistant", "tool"] = Field(...)
    content: str = Field(...)
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(..., description="Model identifier")
    messages: List[ChatMessage] = Field(..., min_length=1)
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, ge=0, le=1)
    max_tokens: Optional[int] = Field(None, ge=1)
    stream: bool = Field(default=False)
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = Field(None, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(None, ge=-2, le=2)
    user: Optional[str] = None
    
    # Additional options passed to Ollama
    options: Optional[Dict[str, Any]] = None


class ChatCompletionChoice(BaseModel):
    """A single completion choice."""
    index: int
    message: ChatMessage
    finish_reason: Optional[Literal["stop", "length", "tool_calls"]] = "stop"


class UsageInfo(BaseModel):
    """Token usage information."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = Field(..., description="Unique completion ID")
    object: str = "chat.completion"
    created: int = Field(..., description="Unix timestamp")
    model: str = Field(..., description="Model used")
    choices: List[ChatCompletionChoice]
    usage: UsageInfo
    
    # Extra metadata
    provider: Optional[str] = None  # 'ollama', 'openrouter'
    node_id: Optional[str] = None  # Which node served this


class ModelInfo(BaseModel):
    """Model information."""
    id: str
    object: str = "model"
    created: int
    owned_by: str
    provider: str  # 'ollama' or 'openrouter'


class ModelList(BaseModel):
    """List of available models."""
    object: str = "list"
    data: List[ModelInfo]
