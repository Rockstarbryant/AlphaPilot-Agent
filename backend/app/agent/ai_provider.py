"""
AI provider abstraction. Per the original spec's own priority ordering,
this is deliberately downstream of the deterministic risk/scoring path —
nothing in app/risk/engine.py or app/strategies/*.py's numeric scoring reads
a value this module produces. Its only job is qualitative narrative on top
of an already-scored, already-risk-checked candidate: comparing two
qualified candidates in plain language, or explaining market context. If
this fails or is unconfigured, strategy scoring and risk validation are
completely unaffected — see docs/RISK_ENGINE.md "Hard stop — independent of
the AI loop" for the same discipline applied to exits.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

settings = get_settings()


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider is unavailable or misconfigured.
    Callers must treat this as 'AI unavailable' per docs/RISK_ENGINE.md #62 —
    never as a reason to guess, block deterministic monitoring, or fall back
    to a stale cached AI opinion."""


@dataclass
class AIAnalysisResult:
    text: str
    model: str


class AIProvider(ABC):
    @abstractmethod
    async def analyze(self, prompt: str, *, max_tokens: int = 400) -> AIAnalysisResult:
        ...

    @abstractmethod
    async def supports_structured_output(self) -> bool:
        ...


class OpenRouterProvider(AIProvider):
    """
    Talks to OpenRouter's OpenAI-compatible chat completions endpoint. The
    model is never hardcoded — configured via OPENROUTER_MODEL — and if it's
    unset or the API key is missing, every call fails loudly with
    AIProviderError rather than silently downgrading functionality, per the
    original spec's explicit instruction on this point.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model

    def _require_config(self):
        if not self.api_key:
            raise AIProviderError("OPENROUTER_API_KEY is not set. AI analysis unavailable.")
        if not self.model:
            raise AIProviderError("OPENROUTER_MODEL is not set. AI analysis unavailable.")

    async def analyze(self, prompt: str, *, max_tokens: int = 400) -> AIAnalysisResult:
        self._require_config()
        async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=30.0) as client:
            try:
                resp = await client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise AIProviderError(f"OpenRouter request failed: {e}") from e

        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise AIProviderError(f"Unexpected OpenRouter response shape: {data}") from e
        return AIAnalysisResult(text=text, model=self.model)

    async def supports_structured_output(self) -> bool:
        """
        Verifies the configured model can be called at all and returns a
        well-formed response. This is a real capability check (a live
        round-trip), not a hardcoded allowlist of model names — per the
        spec's instruction not to assume a specific model exists.
        """
        try:
            await self.analyze("Reply with exactly: OK", max_tokens=5)
            return True
        except AIProviderError:
            return False


def get_ai_provider() -> AIProvider:
    if settings.ai_provider != "openrouter":
        raise AIProviderError(
            f"Unknown AI_PROVIDER '{settings.ai_provider}'. Only 'openrouter' is implemented."
        )
    return OpenRouterProvider()
