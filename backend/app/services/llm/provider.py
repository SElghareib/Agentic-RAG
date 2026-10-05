"""LLM Provider abstraction for Qwen (DashScope API)"""

import asyncio
import logging
from typing import AsyncGenerator, Optional
from dataclasses import dataclass

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured LLM response"""
    content: str
    token_usage: dict
    model: str
    finish_reason: str


class QwenProvider:
    """
    Async client for Qwen models via DashScope API.
    
    Features:
    - Streaming support (SSE)
    - Exponential backoff retries
    - Timeout management
    - Token usage tracking
    """
    
    def __init__(self):
        self.api_key = settings.QWEN_API_KEY
        self.base_url = settings.QWEN_BASE_URL
        self.model = settings.QWEN_MODEL
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.temperature = settings.LLM_TEMPERATURE
        self.timeout = settings.LLM_TIMEOUT
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def chat_completion(
        self,
        messages: list[dict],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse | AsyncGenerator[str, None]:
        """
        Send chat completion request to Qwen.
        
        Args:
            messages: List of message dicts with role/content
            stream: Whether to stream response
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            LLMResponse or async generator of tokens
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        
        logger.debug(f"Sending request to Qwen: {payload}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=self.timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Qwen API error: {response.status} - {error_text}")
                    raise RuntimeError(f"Qwen API error: {response.status}")
                
                if stream:
                    return self._parse_stream(response)
                else:
                    data = await response.json()
                    return self._parse_response(data)
    
    async def _parse_stream(self, response: aiohttp.ClientResponse) -> AsyncGenerator[str, None]:
        """Parse SSE stream from Qwen API"""
        async for line in response.content:
            line = line.decode("utf-8").strip()
            
            if not line.startswith("data:"):
                continue
            
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            
            try:
                import json
                data = json.loads(data_str)
                choices = data.get("choices", [])
                
                if choices and len(choices) > 0:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                        
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse SSE data: {e}")
                continue
    
    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse non-streaming response"""
        choices = data.get("choices", [])
        usage = data.get("usage", {})
        
        if not choices:
            raise ValueError("No choices in LLM response")
        
        choice = choices[0]
        message = choice.get("message", {})
        
        return LLMResponse(
            content=message.get("content", ""),
            token_usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason", "stop"),
        )
    
    async def generate_with_retry(
        self,
        messages: list[dict],
        **kwargs
    ) -> LLMResponse:
        """Convenience method for non-streaming generation with retries"""
        return await self.chat_completion(messages, stream=False, **kwargs)
    
    async def stream_with_retry(
        self,
        messages: list[dict],
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Convenience method for streaming generation with retries"""
        async for token in await self.chat_completion(messages, stream=True, **kwargs):
            yield token
