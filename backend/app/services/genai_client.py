"""GenAI provider client (Pipeline 1 transport).

Provider selection is environment-driven (AI_PROVIDER=gemini|offline).
Gemini is called through the REST API with an API key from the environment;
no key ever lives in code. The validation pipeline never imports this module
for decisions — it is transport + parsing only.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx

from ..config import settings

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class AIProviderError(Exception):
    pass


def extract_json_object(text: str) -> Optional[dict]:
    """Best-effort extraction of the first JSON object from a model answer."""
    if not text:
        return None
    candidate = text.strip()
    fence = _FENCE.search(candidate)
    if fence:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(candidate[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def call_gemini(prompt: str, json_mode: bool = True) -> tuple[Optional[dict], str, int]:
    """Call the Gemini generateContent endpoint.

    Returns (parsed_json_or_None, raw_text, latency_ms). Raises AIProviderError
    on transport/auth failures (which are NOT schema issues).
    """
    if not settings.gemini_api_key:
        raise AIProviderError("GEMINI_API_KEY is not configured")

    url = f"{settings.gemini_api_base}/models/{settings.gemini_model}:generateContent"
    generation_config = {
        "temperature": 0.2,
        "topP": 0.9,
        "maxOutputTokens": 4096,
    }
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
        "safetySettings": [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
        ],
    }
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(url, params={"key": settings.gemini_api_key}, json=payload)
    except httpx.HTTPError as exc:
        raise AIProviderError(f"Gemini request failed: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        detail = response.text[:400]
        raise AIProviderError(f"Gemini API error {response.status_code}: {detail}")

    try:
        data = response.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
        raw_text = "".join(part.get("text", "") for part in parts)
    except (ValueError, KeyError, IndexError) as exc:
        raise AIProviderError(f"Unexpected Gemini response shape: {exc}") from exc

    if not json_mode:
        return None, raw_text, latency_ms
    return extract_json_object(raw_text), raw_text, latency_ms


def call_lovable(prompt: str, json_mode: bool = True) -> tuple[Optional[dict], str, int]:
    """Call the Lovable AI Gateway (OpenAI-compatible chat completions).

    Returns (parsed_json_or_None, raw_text, latency_ms). Raises AIProviderError
    on transport/auth failures (which are NOT schema issues).
    """
    if not settings.lovable_api_key:
        raise AIProviderError("LOVABLE_API_KEY is not configured")

    url = f"{settings.lovable_api_base}/chat/completions"
    payload: dict = {
        "model": settings.lovable_model,
        "messages": [{"role": "user", "content": prompt}],
        # gpt-6-astra requires reasoning and rejects temperature/max_tokens.
        "reasoning_effort": "low",
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {settings.lovable_api_key}",
        "Lovable-API-Key": settings.lovable_api_key,
        "X-Lovable-AIG-SDK": "fetch",
        "Content-Type": "application/json",
    }
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise AIProviderError(f"Lovable AI request failed: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        detail = response.text[:400]
        raise AIProviderError(f"Lovable AI error {response.status_code}: {detail}")

    try:
        data = response.json()
        choices = data.get("choices") or []
        raw_text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    except (ValueError, KeyError, IndexError) as exc:
        raise AIProviderError(f"Unexpected Lovable AI response shape: {exc}") from exc

    if not json_mode:
        return None, raw_text, latency_ms
    return extract_json_object(raw_text), raw_text, latency_ms


def call_ai(prompt: str, json_mode: bool = True) -> tuple[Optional[dict], str, int]:
    """Dispatch to the configured live GenAI provider (lovable | gemini)."""
    provider = settings.resolved_ai_provider
    if provider == "lovable":
        return call_lovable(prompt, json_mode=json_mode)
    if provider == "gemini":
        return call_gemini(prompt, json_mode=json_mode)
    raise AIProviderError(f"No live AI provider configured (effective provider: {provider})")


def provider_status() -> dict:
    provider = settings.resolved_ai_provider
    model = {
        "gemini": settings.gemini_model,
        "lovable": settings.lovable_model,
    }.get(provider, "offline-heuristic-baseline")
    return {
        "configured_provider": settings.ai_provider,
        "effective_provider": provider,
        "model": model,
        "genai_live": provider in ("gemini", "lovable"),
        "note": (
            "Live GenAI pipeline active."
            if provider in ("gemini", "lovable")
            else "Offline heuristic baseline in use (no AI API key configured). "
                 "It is clearly labelled in results and never treated as ground truth."
        ),
    }
