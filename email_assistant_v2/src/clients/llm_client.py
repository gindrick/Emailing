from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional, Type, TypeVar

from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Klient pro LiteLLM proxy - podporuje OpenAI a dalsi poskytovatele."""

    def __init__(self, model: str | None = None):
        self.base_url = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
        self.api_key = os.getenv("LITELLM_API_KEY", os.getenv("LITELLM_MASTER_KEY", "sk-mysecretkey"))
        self.model = model or os.getenv("LITELLM_MODEL", "oai-gpt-4.1-nano")

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        self.instructor_client = instructor.from_openai(self.client, mode=instructor.Mode.JSON)

        logger.info(f"LLMClient inicializovan: {self.base_url}, model={self.model}")

    async def call(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """Standardni chat completion."""
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = False

        return await self.client.chat.completions.create(**kwargs)

    async def call_structured(
        self,
        messages: List[Dict[str, Any]],
        response_model: Type[T],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
    ) -> T:
        """Strukturovany vystup pres Instructor."""
        return await self.instructor_client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
