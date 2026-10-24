"""Core Pydantic v2 data models for NEMESIS Phase 1."""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

ResponseType = Literal["success", "partial", "error", "timeout", "malformed"]


class WorldState(BaseModel):
    """Ground-truth environment state after tool execution."""

    status: str = "none"
    confirmation_id: str | None = None
    booking_id: str | None = None
    hotel_id: str | None = None
    hotels: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolResponse(BaseModel):
    tool_name: str
    call_index: int
    response: dict[str, Any]
    response_type: ResponseType


class TraceStep(BaseModel):
    step_index: int
    agent_thought: str | None = None
    tool_call: dict[str, Any] | None = None
    tool_response: ToolResponse | None = None


class AgentTrace(BaseModel):
    trace_id: str
    scenario_id: str
    steps: list[TraceStep]
    final_output: str
    claimed_success: bool
    world_state: WorldState
    wall_time_ms: int


class Invariant(BaseModel):
    """Predicate that must hold true at the end of a run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    check: Callable[[WorldState, AgentTrace], bool]
    description: str


class State(BaseModel):
    """Named condition that must never occur during or after a run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    check: Callable[[WorldState, AgentTrace], bool]


class TaskRequirement(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    description: str
    invariants: list[Invariant]
    forbidden_states: list[State]
    success_condition: Callable[[AgentTrace], bool]


class Scenario(BaseModel):
    scenario_id: str
    tool_responses: list[ToolResponse]
    environment_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
