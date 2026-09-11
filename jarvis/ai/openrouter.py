from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import requests

logger = logging.getLogger("jarvis.openrouter")


class ModelRole(str, Enum):
    FAST_INTENT = "FAST_INTENT"
    CONVERSATION = "CONVERSATION"
    PLANNING = "PLANNING"
    DEEP_REASONING = "DEEP_REASONING"
    HEAVY_REASONING = "HEAVY_REASONING"
    COMPUTER_AGENT = "COMPUTER_AGENT"
    CODING_AGENT = "CODING_AGENT"
    LIGHT_CODING = "LIGHT_CODING"
    TERMINAL = "TERMINAL"
    VISION = "VISION"
    MULTIMODAL = "MULTIMODAL"
    SAFETY = "SAFETY"


@dataclass
class ModelMetadata:
    id: str
    name: str = ""
    context_length: int = 4096
    input_modalities: List[str] = field(default_factory=lambda: ["text"])
    output_modalities: List[str] = field(default_factory=lambda: ["text"])
    prompt_price: float = 0.0
    completion_price: float = 0.0
    is_free: bool = True
    supports_tools: bool = False
    supports_reasoning: bool = False
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelHealth:
    model_id: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rate_limited_calls: int = 0
    timeout_calls: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""
    last_error_time: float = 0.0
    consecutive_failures: int = 0
    is_available: bool = True

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls

    def record_success(self, latency_ms: float) -> None:
        self.total_calls += 1
        self.successful_calls += 1
        self.total_latency_ms += latency_ms
        self.consecutive_failures = 0
        self.is_available = True

    def record_failure(self, error: str, is_rate_limit: bool = False, is_timeout: bool = False) -> None:
        self.total_calls += 1
        self.failed_calls += 1
        self.consecutive_failures += 1
        self.last_error = str(error)[:200]
        self.last_error_time = time.time()
        if is_rate_limit:
            self.rate_limited_calls += 1
        if is_timeout:
            self.timeout_calls += 1
        # Back off model after 3 consecutive failures for 60 seconds
        if self.consecutive_failures >= 3:
            self.is_available = False

    def check_backoff_expiry(self, backoff_seconds: float = 60.0) -> bool:
        if not self.is_available and (time.time() - self.last_error_time) > backoff_seconds:
            self.is_available = True
            self.consecutive_failures = 0
            return True
        return self.is_available


class QuotaManager:
    """Protects rate limits for free OpenRouter tier.
    
    Tracks requests per minute and daily usage, prioritizing foreground
    user requests over background research/monitoring tasks.
    """

    def __init__(self, max_rpm: int = 20, max_rpd: int = 500) -> None:
        self.max_rpm = max_rpm
        self.max_rpd = max_rpd
        self._request_timestamps: List[float] = []
        self._day_start: float = time.time()
        self._requests_today: int = 0
        self.rate_limit_events: int = 0

    def record_request(self) -> None:
        now = time.time()
        # Reset daily counter if >24 hours
        if now - self._day_start >= 86400:
            self._day_start = now
            self._requests_today = 0
        self._request_timestamps.append(now)
        self._requests_today += 1
        self._prune(now)

    def _prune(self, now: float) -> None:
        one_minute_ago = now - 60.0
        self._request_timestamps = [t for t in self._request_timestamps if t >= one_minute_ago]

    @property
    def current_rpm(self) -> int:
        now = time.time()
        self._prune(now)
        return len(self._request_timestamps)

    def can_request(self, is_foreground: bool = True) -> Tuple[bool, str]:
        now = time.time()
        self._prune(now)
        # Check daily quota
        if self._requests_today >= self.max_rpd:
            return False, f"Daily quota exhausted ({self._requests_today}/{self.max_rpd})"

        # Check RPM
        current_rpm = len(self._request_timestamps)
        if is_foreground:
            if current_rpm >= self.max_rpm:
                return False, f"Rate limit reached ({current_rpm}/{self.max_rpm} RPM)"
            return True, ""
        else:
            # Background tasks yield headroom to foreground (use at most 60% of RPM)
            bg_limit = max(1, int(self.max_rpm * 0.6))
            if current_rpm >= bg_limit:
                return False, f"Background throttled to yield to user ({current_rpm}/{bg_limit} RPM)"
            return True, ""

    def record_rate_limit(self) -> None:
        self.rate_limit_events += 1


class OpenRouterClient:
    """OpenRouter API client with dynamic free-model discovery and role routing."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: Optional[str] = None, app_name: str = "JARVIS") -> None:
        self.api_key = api_key or self._resolve_api_key()
        self.app_name = app_name
        self.catalog: Dict[str, ModelMetadata] = {}
        self.health: Dict[str, ModelHealth] = {}
        self.quota = QuotaManager(max_rpm=25, max_rpd=1000)
        self.last_catalog_refresh: float = 0.0
        self.catalog_cache_ttl: float = 300.0  # 5 minutes

    def _resolve_api_key(self) -> str:
        """Return credentials from process-managed secret storage only.

        Reading ad-hoc key files makes accidental disclosure far too easy and
        prevents a deployment from having one auditable secret boundary.  The
        frontend never sees this value; callers must provide it explicitly or
        configure ``OPENROUTER_API_KEY`` in the process environment.
        """
        return os.environ.get("OPENROUTER_API_KEY", "").strip()

    @property
    def has_valid_key(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-or-"))

    def get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/jarvis-ai-system",
            "X-Title": self.app_name,
            "Content-Type": "application/json",
        }

    def refresh_catalog(self, force: bool = False) -> List[ModelMetadata]:
        now = time.time()
        if not force and self.catalog and (now - self.last_catalog_refresh) < self.catalog_cache_ttl:
            return list(self.catalog.values())

        if not self.has_valid_key:
            logger.warning("[OpenRouter] Cannot refresh catalog: no valid API key")
            return []

        try:
            resp = requests.get(f"{self.BASE_URL}/models", headers=self.get_headers(), timeout=15)
            if resp.status_code != 200:
                logger.error(f"[OpenRouter] Catalog fetch failed HTTP {resp.status_code}: {resp.text[:150]}")
                return list(self.catalog.values())

            data = resp.json().get("data", [])
            new_catalog: Dict[str, ModelMetadata] = {}
            for m in data:
                m_id = m.get("id", "")
                pricing = m.get("pricing", {})
                prompt_p = float(pricing.get("prompt", 0) or 0)
                comp_p = float(pricing.get("completion", 0) or 0)
                # A model qualifies as free if pricing is 0 or it has :free suffix
                is_free = (prompt_p == 0.0 and comp_p == 0.0) or ":free" in m_id

                arch = m.get("architecture", {})
                input_mods = arch.get("input_modalities", ["text"]) or ["text"]
                output_mods = arch.get("output_modalities", ["text"]) or ["text"]

                # Supported parameters inspection
                params = m.get("supported_parameters", []) or []
                supports_tools = "tools" in params or "function_call" in params
                supports_reasoning = "reasoning" in params or "include_reasoning" in params

                meta = ModelMetadata(
                    id=m_id,
                    name=m.get("name", m_id),
                    context_length=int(m.get("context_length", 4096) or 4096),
                    input_modalities=input_mods,
                    output_modalities=output_mods,
                    prompt_price=prompt_p,
                    completion_price=comp_p,
                    is_free=is_free,
                    supports_tools=supports_tools,
                    supports_reasoning=supports_reasoning,
                    raw_data=m,
                )
                new_catalog[m_id] = meta
                if m_id not in self.health:
                    self.health[m_id] = ModelHealth(model_id=m_id)

            self.catalog = new_catalog
            self.last_catalog_refresh = now
            logger.info(f"[OpenRouter] Catalog refreshed: {len(self.catalog)} models, {len(self.get_free_models())} free.")
            return list(self.catalog.values())

        except Exception as exc:
            logger.error(f"[OpenRouter] Catalog refresh exception: {exc}")
            return list(self.catalog.values())

    def get_free_models(self) -> List[ModelMetadata]:
        return [m for m in self.catalog.values() if m.is_free]

    def get_model_health(self, model_id: str) -> ModelHealth:
        if model_id not in self.health:
            self.health[model_id] = ModelHealth(model_id=model_id)
        return self.health[model_id]

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
        timeout: float = 45.0,
    ) -> Dict[str, Any]:
        """Execute chat completion against OpenRouter model with quota & health tracking."""
        can_req, reason = self.quota.can_request(is_foreground=is_foreground)
        if not can_req:
            raise RuntimeError(f"OpenRouter quota blocked: {reason}")

        health = self.get_model_health(model)
        health.check_backoff_expiry()

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        start_t = time.time()
        self.quota.record_request()

        try:
            resp = requests.post(
                f"{self.BASE_URL}/chat/completions",
                headers=self.get_headers(),
                json=payload,
                timeout=timeout,
            )
            latency_ms = (time.time() - start_t) * 1000.0

            if resp.status_code == 200:
                health.record_success(latency_ms)
                return resp.json()

            is_rate_limit = resp.status_code == 429
            if is_rate_limit:
                self.quota.record_rate_limit()

            err_msg = f"HTTP {resp.status_code}: {resp.text[:250]}"
            health.record_failure(err_msg, is_rate_limit=is_rate_limit)
            raise RuntimeError(f"OpenRouter API error ({model}) -> {err_msg}")

        except requests.exceptions.Timeout as te:
            health.record_failure("Timeout", is_timeout=True)
            raise TimeoutError(f"OpenRouter model {model} timed out after {timeout}s") from te
        except Exception as exc:
            if not isinstance(exc, (RuntimeError, TimeoutError)):
                health.record_failure(str(exc))
            raise


class ModelRouter:
    """Role-aware, capability-scoring model router with automatic fallback chains."""

    # Default preferred model candidates per role (will be validated against live catalog)
    PREFERRED_ROLES: Dict[ModelRole, List[str]] = {
        ModelRole.FAST_INTENT: [
            "nvidia/nemotron-3.5-lightning:free",
            "liquid/lfm-2.5-2.6b:free",
            "inclusionai/ling-3.0-flash-sante:free",
            "inclusionai/ling-3.0-flash-fin:free",
        ],
        ModelRole.CONVERSATION: [
            "google/gemma-4-26b-a4b-it:free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "thinkingmachines/inkling:free",
        ],
        ModelRole.PLANNING: [
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "google/gemma-4-31b-it:free",
        ],
        ModelRole.DEEP_REASONING: [
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        ],
        ModelRole.HEAVY_REASONING: [
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        ModelRole.COMPUTER_AGENT: [
            "poolside/laguna-s-2.1:free",
            "cohere/north-mini-code:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        ModelRole.CODING_AGENT: [
            "poolside/laguna-s-2.1:free",
            "cohere/north-mini-code:free",
            "poolside/laguna-xs-2.1:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        ModelRole.LIGHT_CODING: [
            "poolside/laguna-xs-2.1:free",
            "cohere/north-mini-code:free",
            "poolside/laguna-s-2.1:free",
        ],
        ModelRole.TERMINAL: [
            "cohere/north-mini-code:free",
            "poolside/laguna-xs-2.1:free",
            "poolside/laguna-s-2.1:free",
        ],
        ModelRole.VISION: [
            "google/gemma-4-26b-a4b-it:free",
            "google/gemma-4-31b-it:free",
            "dots-studio/dots-3-note-preview:free",
            "thinkingmachines/inkling:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        ],
        ModelRole.MULTIMODAL: [
            "thinkingmachines/inkling:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "google/gemma-4-26b-a4b-it:free",
            "thinkingmachines/inkling-small:free",
        ],
        ModelRole.SAFETY: [
            "nvidia/nemotron-3.5-content-safety:free",
            "nvidia/nemotron-3.5-lightning:free",
        ],
    }

    def __init__(self, client: OpenRouterClient) -> None:
        self.client = client
        self._role_overrides: Dict[ModelRole, str] = {}

    def set_role_override(self, role: ModelRole, model_id: str) -> None:
        self._role_overrides[role] = model_id

    def select_model_chain(
        self,
        role: ModelRole,
        requires_vision: bool = False,
        requires_tools: bool = False,
    ) -> List[str]:
        """Return prioritized list of compatible models for the role."""
        # Refresh catalog if needed
        self.client.refresh_catalog()
        free_models = {m.id: m for m in self.client.get_free_models()}

        chain: List[str] = []

        # 1. Check manual override
        if role in self._role_overrides:
            override = self._role_overrides[role]
            if override in free_models or override in self.client.catalog:
                chain.append(override)

        # 2. Add role candidates from preferences if available and free
        candidates = self.PREFERRED_ROLES.get(role, [])
        for c in candidates:
            if c in free_models:
                meta = free_models[c]
                health = self.client.get_model_health(c)
                health.check_backoff_expiry()
                if requires_vision and "image" not in meta.input_modalities:
                    continue
                if health.is_available and c not in chain:
                    chain.append(c)

        # 3. Dynamic search among all free models matching requirements if chain empty
        if not chain:
            for m_id, meta in free_models.items():
                if requires_vision and "image" not in meta.input_modalities:
                    continue
                health = self.client.get_model_health(m_id)
                health.check_backoff_expiry()
                if health.is_available and m_id not in chain:
                    chain.append(m_id)

        # 4. Fallback to any remaining models if all are currently backed off
        if not chain and candidates:
            for c in candidates:
                if c in self.client.catalog and c not in chain:
                    chain.append(c)

        return chain

    def execute_with_fallback(
        self,
        role: ModelRole,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        is_foreground: bool = True,
        timeout: float = 45.0,
    ) -> Tuple[Dict[str, Any], str]:
        """Execute chat completion trying the primary model and falling back gracefully."""
        requires_vision = any(
            isinstance(m.get("content"), list) and any(
                isinstance(part, dict) and part.get("type") in ("image", "image_url")
                for part in m.get("content", [])
            )
            for m in messages
        )
        requires_tools = bool(tools)

        chain = self.select_model_chain(
            role=role,
            requires_vision=requires_vision,
            requires_tools=requires_tools,
        )

        if not chain:
            raise RuntimeError(f"No suitable models available for role {role.value}")

        last_error: Optional[Exception] = None
        for model_id in chain:
            try:
                logger.info(f"[ModelRouter] Trying {role.value} -> {model_id}")
                resp = self.client.chat_completion(
                    model=model_id,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    is_foreground=is_foreground,
                    timeout=timeout,
                )
                return resp, model_id
            except Exception as exc:
                logger.warning(f"[ModelRouter] Model {model_id} failed for {role.value}: {exc}")
                last_error = exc
                continue

        raise RuntimeError(f"All models in fallback chain for {role.value} failed. Last error: {last_error}")
