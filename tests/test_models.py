"""Unit tests for NEMESIS core Pydantic models."""

import pytest
from pydantic import ValidationError

from nemesis.models import (
    AgentTrace,
    Invariant,
    Scenario,
    State,
    TaskRequirement,
    ToolResponse,
    TraceStep,
    WorldState,
)


def _sample_trace(**overrides) -> AgentTrace:
    data = {
        "trace_id": "trc-1",
        "scenario_id": "scn-1",
        "steps": [],
        "final_output": "Booking confirmed.",
        "claimed_success": True,
        "world_state": WorldState(status="confirmed", confirmation_id="CNF-1"),
        "wall_time_ms": 12,
    }
    data.update(overrides)
    return AgentTrace(**data)


def test_world_state_defaults() -> None:
    state = WorldState()
    assert state.status == "none"
    assert state.confirmation_id is None
    assert state.hotels == []
    assert state.extra == {}


def test_tool_response_accepts_all_response_types() -> None:
    for response_type in ("success", "partial", "error", "timeout", "malformed"):
        payload = ToolResponse(
            tool_name="search_hotels",
            call_index=0,
            response={"ok": True},
            response_type=response_type,
        )
        assert payload.response_type == response_type


def test_tool_response_rejects_unknown_response_type() -> None:
    with pytest.raises(ValidationError):
        ToolResponse(
            tool_name="search_hotels",
            call_index=0,
            response={},
            response_type="unknown",  # type: ignore[arg-type]
        )


def test_trace_step_optional_fields() -> None:
    step = TraceStep(step_index=0)
    assert step.agent_thought is None
    assert step.tool_call is None
    assert step.tool_response is None


def test_agent_trace_roundtrip() -> None:
    step = TraceStep(
        step_index=0,
        agent_thought="search first",
        tool_call={"name": "search_hotels", "args": {"city": "Austin"}},
        tool_response=ToolResponse(
            tool_name="search_hotels",
            call_index=0,
            response={"hotels": []},
            response_type="success",
        ),
    )
    trace = _sample_trace(steps=[step])
    restored = AgentTrace.model_validate(trace.model_dump())
    assert restored.steps[0].tool_response is not None
    assert restored.steps[0].tool_response.tool_name == "search_hotels"
    assert restored.world_state.confirmation_id == "CNF-1"


def test_scenario_preserves_ordered_tool_responses() -> None:
    scenario = Scenario(
        scenario_id="scn-adv-1",
        tool_responses=[
            ToolResponse(
                tool_name="request_booking",
                call_index=0,
                response={"status": "pending"},
                response_type="partial",
            ),
            ToolResponse(
                tool_name="confirm_booking",
                call_index=1,
                response={"error": "timeout"},
                response_type="timeout",
            ),
        ],
        environment_config={"city": "Austin"},
        metadata={"generator": "phase1-test"},
    )
    assert [item.tool_name for item in scenario.tool_responses] == [
        "request_booking",
        "confirm_booking",
    ]
    dumped = scenario.model_dump()
    assert dumped["environment_config"]["city"] == "Austin"


def test_invariant_and_task_requirement_callables() -> None:
    invariant = Invariant(
        name="always_true",
        check=lambda _world, _trace: True,
        description="Always holds.",
    )
    forbidden = State(
        name="never",
        description="Never occurs.",
        check=lambda _world, _trace: False,
    )
    task = TaskRequirement(
        task_id="demo",
        description="Demo task",
        invariants=[invariant],
        forbidden_states=[forbidden],
        success_condition=lambda trace: trace.claimed_success,
    )
    trace = _sample_trace()
    assert task.invariants[0].check(trace.world_state, trace) is True
    assert task.forbidden_states[0].check(trace.world_state, trace) is False
    assert task.success_condition(trace) is True
