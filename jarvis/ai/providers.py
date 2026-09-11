from __future__ import annotations

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from jarvis.ai.openrouter import OpenRouterClient, ModelRouter, ModelRole
from jarvis.ai.ollama import OllamaAdapter

logger = logging.getLogger("jarvis.providers")


class BaseAIProvider(ABC):
    """Abstract provider interface."""

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        role: ModelRole = ModelRole.CONVERSATION,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
    ) -> Dict[str, Any]:
        pass


class OpenRouterProvider(BaseAIProvider):
    """OpenRouter provider with role-based free model routing."""

    def __init__(self, client: Optional[OpenRouterClient] = None) -> None:
        self.client = client or OpenRouterClient()
        self.router = ModelRouter(self.client)

    def name(self) -> str:
        return "openrouter"

    def is_available(self) -> bool:
        return self.client.has_valid_key

    def chat(
        self,
        messages: List[Dict[str, Any]],
        role: ModelRole = ModelRole.CONVERSATION,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
    ) -> Dict[str, Any]:
        resp, used_model = self.router.execute_with_fallback(
            role=role,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            is_foreground=is_foreground,
        )
        return {"provider": "openrouter", "model": used_model, "response": resp}


class GroqProvider(BaseAIProvider):
    """Groq Cloud provider wrapping OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "openai/gpt-oss-120b") -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.default_model = default_model
        self.fallbacks = ["openai/gpt-oss-20b", "allam-2-7b", "qwen/qwen3.6-27b"]

    def name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        role: ModelRole = ModelRole.CONVERSATION,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
    ) -> Dict[str, Any]:
        import openai

        client = openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=self.api_key,
            timeout=30.0,
        )
        models_to_try = [self.default_model, *self.fallbacks]
        last_err: Optional[Exception] = None
        for m in models_to_try:
            try:
                kwargs: Dict[str, Any] = {
                    "model": m,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                res = client.chat.completions.create(**kwargs)
                return {
                    "provider": "groq",
                    "model": m,
                    "response": res.model_dump() if hasattr(res, "model_dump") else dict(res),
                }
            except Exception as e:
                logger.warning(f"[GroqProvider] Model {m} failed: {e}")
                last_err = e
        raise RuntimeError(f"All Groq models failed: {last_err}")


class GeminiProvider(BaseAIProvider):
    """Gemini Provider wrapping OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "gemini-1.5-flash") -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.default_model = default_model
        self.fallbacks = ["gemini-2.0-flash", "gemini-1.5-flash-latest"]

    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        role: ModelRole = ModelRole.CONVERSATION,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
    ) -> Dict[str, Any]:
        import openai

        client = openai.OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=self.api_key,
            timeout=30.0,
        )
        models_to_try = [self.default_model, *self.fallbacks]
        last_err: Optional[Exception] = None
        for m in models_to_try:
            try:
                kwargs: Dict[str, Any] = {
                    "model": m,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                res = client.chat.completions.create(**kwargs)
                return {
                    "provider": "gemini",
                    "model": m,
                    "response": res.model_dump() if hasattr(res, "model_dump") else dict(res),
                }
            except Exception as e:
                logger.warning(f"[GeminiProvider] Model {m} failed: {e}")
                last_err = e
        raise RuntimeError(f"All Gemini models failed: {last_err}")


class OllamaProvider(BaseAIProvider):
    """Local Ollama Provider."""

    def __init__(self, adapter: Optional[OllamaAdapter] = None) -> None:
        self.adapter = adapter or OllamaAdapter()

    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        try:
            return self.adapter.health().ready
        except Exception:
            return False

    def chat(
        self,
        messages: List[Dict[str, Any]],
        role: ModelRole = ModelRole.CONVERSATION,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
    ) -> Dict[str, Any]:
        model = "qwen3:4b"
        content = self.adapter.chat(messages=messages, model=model)
        fake_response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }]
        }
        return {"provider": "ollama", "model": model, "response": fake_response}


class ProviderRouter:
    """Master AI Provider Router.
    
    Tries OpenRouter (with role-based free models) first.
    Falls back to Groq -> Gemini -> Ollama if OpenRouter is unreachable.
    """

    def __init__(
        self,
        openrouter: Optional[OpenRouterProvider] = None,
        groq: Optional[GroqProvider] = None,
        gemini: Optional[GeminiProvider] = None,
        ollama: Optional[OllamaProvider] = None,
    ) -> None:
        self.openrouter = openrouter or OpenRouterProvider()
        self.groq = groq or GroqProvider()
        self.gemini = gemini or GeminiProvider()
        self.ollama = ollama or OllamaProvider()

    def chat(
        self,
        messages: List[Dict[str, Any]],
        role: ModelRole = ModelRole.CONVERSATION,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
    ) -> Dict[str, Any]:
        # Try OpenRouter first (dynamic free model pool)
        if self.openrouter.is_available():
            try:
                return self.openrouter.chat(
                    messages=messages,
                    role=role,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    is_foreground=is_foreground,
                )
            except Exception as e:
                logger.warning(f"[ProviderRouter] OpenRouter failed for role {role.value}: {e}. Falling back...")

        # Fallback 1: Groq
        if self.groq.is_available():
            try:
                return self.groq.chat(
                    messages=messages,
                    role=role,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    is_foreground=is_foreground,
                )
            except Exception as e:
                logger.warning(f"[ProviderRouter] Groq failed: {e}. Falling back...")

        # Fallback 2: Gemini
        if self.gemini.is_available():
            try:
                return self.gemini.chat(
                    messages=messages,
                    role=role,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    is_foreground=is_foreground,
                )
            except Exception as e:
                logger.warning(f"[ProviderRouter] Gemini failed: {e}. Falling back...")

        # Fallback 3: Local Ollama
        if self.ollama.is_available():
            try:
                return self.ollama.chat(
                    messages=messages,
                    role=role,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    is_foreground=is_foreground,
                )
            except Exception as e:
                logger.error(f"[ProviderRouter] Ollama failed: {e}")

        raise RuntimeError("All AI providers (OpenRouter, Groq, Gemini, Ollama) failed or unavailable.")
