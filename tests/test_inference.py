from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from nemesis.api.config import settings
from nemesis.api.services.inference import complete_json


def test_groq_provider_uses_groq_sdk_and_configured_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"answer":"grounded"}')
                    )
                ]
            )

    class FakeGroq:
        def __init__(self, *, api_key: str):
            captured["api_key"] = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")
    monkeypatch.setattr("nemesis.api.services.inference.Groq", FakeGroq)

    result = complete_json(
        provider="groq",
        messages=[{"role": "user", "content": "test"}],
    )

    assert result.provider == "groq"
    assert result.model == settings.groq_model
    assert captured["api_key"] == "test-only-key"
    assert captured["model"] == settings.groq_model
    assert captured["response_format"] == {"type": "json_object"}


def test_ollama_provider_routes_to_local_http_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"message": {"content": '{"answer":"local"}'}}

    def fake_post(url, *, json, timeout):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("nemesis.api.services.inference.httpx.post", fake_post)

    result = complete_json(
        provider="ollama",
        model="cloud-model-must-not-be-used",
        messages=[{"role": "user", "content": "test"}],
    )

    assert result.provider == "ollama"
    assert result.model == "gemma4:e2b"
    assert result.model == settings.ollama_model
    assert captured["url"] == f"{settings.ollama_base_url}/api/chat"
    assert captured["json"]["model"] == settings.ollama_model
    assert captured["json"]["stream"] is False
    assert captured["json"]["format"] == "json"


def test_groq_provider_accepts_explicit_adjudicator_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"passed":true}')
                    )
                ]
            )

    class FakeGroq:
        def __init__(self, *, api_key: str):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")
    monkeypatch.setattr("nemesis.api.services.inference.Groq", FakeGroq)

    result = complete_json(
        provider="groq",
        model="independent-critic-model",
        messages=[{"role": "user", "content": "evaluate"}],
    )

    assert captured["model"] == "independent-critic-model"
    assert result.model == "independent-critic-model"


def test_local_provider_rejects_non_loopback_ollama_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "nemesis.api.services.inference.settings",
        replace(settings, ollama_base_url="http://ollama.example.test:11434"),
    )
    monkeypatch.setattr(
        "nemesis.api.services.inference.httpx.post",
        lambda *_args, **_kwargs: pytest.fail("Local mode must not make outbound requests"),
    )

    with pytest.raises(HTTPException) as error:
        complete_json(
            provider="ollama",
            messages=[{"role": "user", "content": "local test"}],
        )

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "ollama_must_be_local"
