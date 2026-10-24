"""Agent execution harness with scenario tool interception and free-tier rate limiting."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Protocol

from dotenv import load_dotenv

from nemesis.models import (
    AgentTrace,
    Scenario,
    TaskRequirement,
    ToolResponse,
    TraceStep,
    WorldState,
)
from nemesis.tasks.booking import BOOKING_TOOLS, initial_world_state

# Groq free-tier safe ceiling for agents / generator / minimizer: 30 RPM.
DEFAULT_REQUESTS_PER_MINUTE = 30.0
DEFAULT_GROQ_MODEL = "groq/openai/gpt-oss-20b"
load_dotenv(Path(__file__).resolve().parents[1] / ".secrets" / ".env")


class SupportsAgentStep(Protocol):
    """Minimal agent interface consumed by ``AgentRunner``."""

    def reset(self) -> None: ...

    def initial_messages(
        self,
        task_description: str,
        city: str = "Austin",
    ) -> list[dict[str, Any]]: ...

    def step(
        self,
        messages: list[dict[str, Any]],
        *,
        mock_llm: bool = False,
    ) -> Any: ...


class RateLimiter:
    """Hard minimum spacing between LLM calls (plus optional exponential backoff)."""

    def __init__(self, requests_per_minute: float = DEFAULT_REQUESTS_PER_MINUTE) -> None:
        self.min_interval_s = 60.0 / max(requests_per_minute, 0.1)
        self._last_request_at = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            self._wait_unlocked()

    def call(self, function: Callable[[], Any]) -> Any:
        """Reserve a request slot and hold it until the request completes."""
        with self._lock:
            self._wait_unlocked()
            return function()

    def _wait_unlocked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if self._last_request_at > 0 and elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_request_at = time.monotonic()

    def backoff(self, attempt: int) -> None:
        # attempt is 1-indexed; caps at ~32s extra delay.
        delay = min(2 ** max(attempt - 1, 0), 32)
        with self._lock:
            time.sleep(delay)
            self._last_request_at = time.monotonic()


GROQ_RATE_LIMITER = RateLimiter(DEFAULT_REQUESTS_PER_MINUTE)
InferenceProvider = Literal["groq", "ollama"]
_ACTIVE_INFERENCE_PROVIDER: ContextVar[InferenceProvider] = ContextVar(
    "nemesis_inference_provider", default="groq"
)


@contextmanager
def use_inference_provider(provider: InferenceProvider) -> Iterator[None]:
    """Scope all pipeline model calls to Groq or loopback-only Ollama."""
    token = _ACTIVE_INFERENCE_PROVIDER.set(provider)
    try:
        yield
    finally:
        _ACTIVE_INFERENCE_PROVIDER.reset(token)


def groq_completion(*, model: str | None = None, **kwargs: Any) -> Any:
    """Route a pipeline model call to its scoped cloud or local provider."""
    import litellm

    if _ACTIVE_INFERENCE_PROVIDER.get() == "ollama":
        from nemesis.api.config import settings

        try:
            api_base = settings.require_loopback_ollama_url()
        except ValueError as exc:
            raise RuntimeError("Local mode rejected a non-loopback Ollama URL.") from exc
        local_kwargs = dict(kwargs)
        local_kwargs.pop("model", None)
        local_kwargs.pop("api_key", None)
        local_kwargs.pop("api_base", None)
        return litellm.completion(
            model=f"ollama_chat/{settings.ollama_model}",
            api_base=api_base,
            api_key="ollama",
            **local_kwargs,
        )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    return GROQ_RATE_LIMITER.call(
        lambda: litellm.completion(
            model=model or os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL),
            api_key=api_key,
            **kwargs,
        )
    )


class AgentRunner:
    """Run an agent against a scenario, recording an ``AgentTrace``.

    When ``mock_llm=True``, no remote LLM calls are made (instant / $0 tests).
    Otherwise LLM calls are spaced to stay under the free-tier RPM budget.
    """

    def __init__(
        self,
        *,
        requests_per_minute: float = DEFAULT_REQUESTS_PER_MINUTE,
        max_steps: int = 12,
        max_retries: int = 5,
    ) -> None:
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.max_steps = max_steps
        self.max_retries = max_retries

    def run(
        self,
        agent: SupportsAgentStep,
        scenario: Scenario,
        task: TaskRequirement,
        *,
        mock_llm: bool = False,
    ) -> AgentTrace:
        started = time.perf_counter()
        agent.reset()

        world = initial_world_state()
        city = str(scenario.environment_config.get("city", "Austin"))
        messages = agent.initial_messages(task.description, city=city)

        steps: list[TraceStep] = []
        call_counts: dict[str, int] = defaultdict(int)
        scenario_by_key = {
            (item.tool_name, item.call_index): item for item in scenario.tool_responses
        }

        final_output = "Agent stopped without a final answer."
        claimed_success = False

        for step_index in range(self.max_steps):
            action = self._safe_step(agent, messages, mock_llm=mock_llm)

            if action.tool_call is None:
                final_output = action.final_output or final_output
                claimed_success = bool(action.claimed_success)
                steps.append(
                    TraceStep(
                        step_index=step_index,
                        agent_thought=action.thought,
                        tool_call=None,
                        tool_response=None,
                    )
                )
                break

            tool_name = str(action.tool_call.get("name", ""))
            arguments = dict(action.tool_call.get("arguments") or {})
            call_index = call_counts[tool_name]
            call_counts[tool_name] += 1

            tool_response = self._resolve_tool_response(
                tool_name=tool_name,
                call_index=call_index,
                arguments=arguments,
                world=world,
                scenario_by_key=scenario_by_key,
            )

            steps.append(
                TraceStep(
                    step_index=step_index,
                    agent_thought=action.thought,
                    tool_call={"name": tool_name, "arguments": arguments},
                    tool_response=tool_response,
                )
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": action.thought,
                    "tool_calls": [
                        {
                            "id": f"call_{step_index}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call_{step_index}",
                    "name": tool_name,
                    "content": json.dumps(tool_response.response),
                }
            )
        else:
            final_output = "Agent exceeded max steps."
            claimed_success = False

        wall_time_ms = int((time.perf_counter() - started) * 1000)
        return AgentTrace(
            trace_id=f"trc-{uuid.uuid4().hex[:12]}",
            scenario_id=scenario.scenario_id,
            steps=steps,
            final_output=final_output,
            claimed_success=claimed_success,
            world_state=world,
            wall_time_ms=wall_time_ms,
        )

    def _safe_step(
        self,
        agent: SupportsAgentStep,
        messages: list[dict[str, Any]],
        *,
        mock_llm: bool,
    ) -> Any:
        if mock_llm:
            return agent.step(messages, mock_llm=True)

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.rate_limiter.wait()
            try:
                return agent.step(messages, mock_llm=False)
            except Exception as exc:  # noqa: BLE001 - retry free-tier / transient LLM errors
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self.rate_limiter.backoff(attempt)

        assert last_error is not None
        raise last_error

    def _resolve_tool_response(
        self,
        *,
        tool_name: str,
        call_index: int,
        arguments: dict[str, Any],
        world: WorldState,
        scenario_by_key: dict[tuple[str, int], ToolResponse],
    ) -> ToolResponse:
        scripted = scenario_by_key.get((tool_name, call_index))
        if scripted is not None:
            self._apply_response_to_world(world, scripted.response)
            return scripted

        handler = BOOKING_TOOLS.get(tool_name)
        if handler is None:
            response = {"ok": False, "error": f"unknown_tool:{tool_name}"}
            return ToolResponse(
                tool_name=tool_name,
                call_index=call_index,
                response=response,
                response_type="error",
            )

        response = handler(world, **arguments)
        return ToolResponse(
            tool_name=tool_name,
            call_index=call_index,
            response=response,
            response_type="success",
        )

    @staticmethod
    def _apply_response_to_world(world: WorldState, response: dict[str, Any]) -> None:
        """Mirror scripted tool payloads into ground-truth world state."""
        if "status" in response and response["status"] is not None:
            world.status = str(response["status"])
        if "confirmation_id" in response:
            world.confirmation_id = response["confirmation_id"]
        if "booking_id" in response:
            world.booking_id = response["booking_id"]
        if "hotel_id" in response:
            world.hotel_id = response["hotel_id"]
        if "hotels" in response and isinstance(response["hotels"], list):
            world.hotels = list(response["hotels"])
