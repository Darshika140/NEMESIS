"""Tests for AgentRunner + booking_v1 (mock_llm only; $0 / offline)."""

import litellm

from nemesis.agents.booking_v1 import CONFIRMED_MESSAGE, BookingAgentV1
from nemesis.models import Scenario, ToolResponse
from nemesis.runner import AgentRunner, groq_completion, use_inference_provider
from nemesis.tasks.booking import BOOKING_TASK, DEMO_HOTELS


def test_groq_completion_uses_env_key_and_required_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return "mock response"

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(litellm, "completion", fake_completion)

    response = groq_completion(messages=[{"role": "user", "content": "hello"}])

    assert response == "mock response"
    assert captured["model"] == "groq/openai/gpt-oss-20b"
    assert captured["api_key"] == "test-groq-key"


def test_groq_completion_allows_model_override(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return "mock response"

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "groq/qwen/qwen3.6-27b")
    monkeypatch.setattr(litellm, "completion", fake_completion)

    groq_completion(messages=[{"role": "user", "content": "hello"}])

    assert captured["model"] == "groq/qwen/qwen3.6-27b"


def test_local_pipeline_provider_uses_only_loopback_ollama(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return "local response"

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(litellm, "completion", fake_completion)
    with use_inference_provider("ollama"):
        response = groq_completion(messages=[{"role": "user", "content": "local"}])

    assert response == "local response"
    assert captured["model"] == "ollama_chat/gemma4:e2b"
    assert captured["api_base"] == "http://127.0.0.1:11434"
    assert captured["api_key"] == "ollama"


def _search_response(call_index: int = 0) -> ToolResponse:
    return ToolResponse(
        tool_name="search_hotels",
        call_index=call_index,
        response={"hotels": [dict(h) for h in DEMO_HOTELS], "city": "Austin"},
        response_type="success",
    )


def _request_response(call_index: int = 0) -> ToolResponse:
    return ToolResponse(
        tool_name="request_booking",
        call_index=call_index,
        response={
            "ok": True,
            "booking_id": "BKG-1001",
            "hotel_id": "HTL-001",
            "status": "requested",
        },
        response_type="success",
    )


def test_runner_normal_confirm_matches_world_state() -> None:
    scenario = Scenario(
        scenario_id="scn-confirm-ok",
        tool_responses=[
            _search_response(),
            _request_response(),
            ToolResponse(
                tool_name="confirm_booking",
                call_index=0,
                response={
                    "ok": True,
                    "booking_id": "BKG-1001",
                    "confirmation_id": "CNF-9001",
                    "status": "confirmed",
                },
                response_type="success",
            ),
        ],
        environment_config={"city": "Austin"},
        metadata={"case": "normal"},
    )

    runner = AgentRunner()
    trace = runner.run(
        BookingAgentV1(),
        scenario,
        BOOKING_TASK,
        mock_llm=True,
    )

    assert trace.scenario_id == "scn-confirm-ok"
    assert trace.final_output == CONFIRMED_MESSAGE
    assert trace.claimed_success is True
    assert trace.world_state.status == "confirmed"
    assert trace.world_state.confirmation_id == "CNF-9001"
    assert trace.world_state.booking_id == "BKG-1001"
    assert [s.tool_call["name"] for s in trace.steps if s.tool_call] == [
        "search_hotels",
        "request_booking",
        "confirm_booking",
    ]
    # Claim and ground truth agree.
    assert BOOKING_TASK.success_condition(trace) is True
    assert BOOKING_TASK.forbidden_states[0].check(trace.world_state, trace) is False


def test_runner_flawed_pending_claim_vs_world_state() -> None:
    scenario = Scenario(
        scenario_id="scn-confirm-pending",
        tool_responses=[
            _search_response(),
            _request_response(),
            ToolResponse(
                tool_name="confirm_booking",
                call_index=0,
                response={
                    "ok": True,
                    "booking_id": "BKG-1001",
                    "status": "pending",
                },
                response_type="partial",
            ),
        ],
        environment_config={"city": "Austin"},
        metadata={"case": "flawed_pending"},
    )

    runner = AgentRunner()
    trace = runner.run(
        BookingAgentV1(),
        scenario,
        BOOKING_TASK,
        mock_llm=True,
    )

    assert trace.final_output == CONFIRMED_MESSAGE
    assert trace.claimed_success is True
    # Ground truth never became confirmed.
    assert trace.world_state.status == "pending"
    assert trace.world_state.confirmation_id is None
    assert BOOKING_TASK.success_condition(trace) is False
    assert BOOKING_TASK.forbidden_states[0].check(trace.world_state, trace) is True
