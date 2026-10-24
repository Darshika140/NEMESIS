"""Single allow-listed inference boundary for Groq and local Ollama."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from fastapi import HTTPException
from groq import APIError, Groq

from nemesis.api.config import settings

Provider = Literal["groq", "ollama"]


@dataclass(frozen=True)
class InferenceResult:
    content: str
    provider: Provider
    model: str


def _decode_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "invalid_model_json",
                "message": "Selected model did not return valid JSON.",
            },
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "invalid_model_shape",
                "message": "Selected model returned JSON that was not an object.",
            },
        )
    return payload


def _validate_local_ollama_url() -> str:
    """Reject non-loopback Ollama hosts so Local mode cannot send data outward."""
    try:
        return settings.require_loopback_ollama_url()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ollama_must_be_local",
                "message": "Local mode only permits an unauthenticated loopback Ollama URL.",
            },
        ) from exc


def complete_json(
    *,
    provider: Provider,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    model: str | None = None,
) -> InferenceResult:
    """Return JSON through Groq or a loopback-only Ollama security boundary."""
    if provider not in ("groq", "ollama"):
        raise HTTPException(
            status_code=400,
            detail={"code": "unsupported_provider", "message": "Inference provider is not allowed."},
        )
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "groq_api_key_missing",
                    "message": "Set GROQ_API_KEY in the backend environment to use Groq.",
                },
            )
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=model or settings.groq_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )
        except APIError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "groq_request_failed",
                    "message": "Groq inference failed; check the API key, model, and quota.",
                },
            ) from exc
        if not response.choices:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "empty_groq_response",
                    "message": "Groq returned no completion choices.",
                },
            )
        content = response.choices[0].message.content or ""
        _decode_json(content)
        return InferenceResult(content, provider, model or settings.groq_model)

    ollama_url = _validate_local_ollama_url()
    try:
        response = httpx.post(
            f"{ollama_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {"temperature": temperature},
            },
            timeout=httpx.Timeout(120.0, connect=3.0),
        )
        response.raise_for_status()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ollama_unavailable",
                "message": (
                    "Local Ollama is unavailable. Start Ollama and pull the configured "
                    "model before selecting Local mode."
                ),
            },
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "ollama_timeout", "message": "Local Ollama timed out."},
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "ollama_request_failed",
                "message": f"Local Ollama returned HTTP {exc.response.status_code}.",
            },
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "invalid_ollama_response",
                "message": "Local Ollama returned an invalid JSON response.",
            },
        ) from exc
    message = body.get("message") if isinstance(body, dict) else None
    content = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(content, str) or not content:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "invalid_ollama_response",
                "message": "Local Ollama returned no assistant content.",
            },
        )
    _decode_json(content)
    return InferenceResult(content, provider, settings.ollama_model)
