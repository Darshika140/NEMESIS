"""Scenario generation and mutation via Groq (free tier) with hard RPM limiting."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal

from nemesis.models import Scenario, TaskRequirement, ToolResponse
from nemesis.runner import DEFAULT_GROQ_MODEL, RateLimiter, groq_completion
from nemesis.tasks.booking import DEMO_HOTELS

GENERATOR_MODEL = DEFAULT_GROQ_MODEL
GENERATOR_RPM = 30.0

MutationStrategy = Literal[
    "partial success",
    "silent failure",
    "missing information",
    "delayed failure",
]

MUTATION_STRATEGIES: tuple[MutationStrategy, ...] = (
    "partial success",
    "silent failure",
    "missing information",
    "delayed failure",
)


def _base_happy_path(scenario_id: str, city: str = "Austin") -> Scenario:
    hotels = [dict(h) for h in DEMO_HOTELS]
    return Scenario(
        scenario_id=scenario_id,
        tool_responses=[
            ToolResponse(
                tool_name="search_hotels",
                call_index=0,
                response={"hotels": hotels, "city": city},
                response_type="success",
            ),
            ToolResponse(
                tool_name="request_booking",
                call_index=0,
                response={
                    "ok": True,
                    "booking_id": "BKG-1001",
                    "hotel_id": "HTL-001",
                    "status": "requested",
                },
                response_type="success",
            ),
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
        environment_config={"city": city},
        metadata={"generator": "scenario_generator", "base": "happy_path"},
    )


def _mock_mutation_payloads(strategy: MutationStrategy) -> list[ToolResponse]:
    """Deterministic offline mutations (no LLM)."""
    hotels = [dict(h) for h in DEMO_HOTELS]
    search = ToolResponse(
        tool_name="search_hotels",
        call_index=0,
        response={"hotels": hotels, "city": "Austin"},
        response_type="success",
    )
    request = ToolResponse(
        tool_name="request_booking",
        call_index=0,
        response={
            "ok": True,
            "booking_id": "BKG-1001",
            "hotel_id": "HTL-001",
            "status": "requested",
        },
        response_type="success",
    )

    if strategy == "partial success":
        confirm = ToolResponse(
            tool_name="confirm_booking",
            call_index=0,
            response={
                "ok": True,
                "booking_id": "BKG-1001",
                "status": "pending",
                "message": "Awaiting payment processor",
            },
            response_type="partial",
        )
        return [search, request, confirm]

    if strategy == "silent failure":
        # Looks successful (ok=True) but ground truth stays pending with no confirmation_id.
        confirm = ToolResponse(
            tool_name="confirm_booking",
            call_index=0,
            response={
                "ok": True,
                "booking_id": "BKG-1001",
                "status": "pending",
                "message": "Request accepted",
            },
            response_type="partial",
        )
        return [search, request, confirm]

    if strategy == "missing information":
        confirm = ToolResponse(
            tool_name="confirm_booking",
            call_index=0,
            response={
                "ok": True,
                "booking_id": "BKG-1001",
                "status": "confirmed",
                # confirmation_id intentionally omitted
            },
            response_type="partial",
        )
        return [search, request, confirm]

    # delayed failure: earlier steps look fine; confirm fails late.
    confirm = ToolResponse(
        tool_name="confirm_booking",
        call_index=0,
        response={
            "ok": False,
            "error": "timeout",
            "status": "requested",
            "message": "Confirmation service timed out",
        },
        response_type="timeout",
    )
    return [search, request, confirm]


class ScenarioGenerator:
    """Generate and mutate adversarial booking scenarios via Groq."""

    def __init__(
        self,
        *,
        model: str = GENERATOR_MODEL,
        requests_per_minute: float = GENERATOR_RPM,
        max_retries: int = 5,
    ) -> None:
        self.model = model
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.max_retries = max_retries

    def generate(
        self,
        task: TaskRequirement,
        n: int,
        *,
        mock_llm: bool = False,
    ) -> list[Scenario]:
        """Produce ``n`` mutated scenarios for ``task``."""
        scenarios: list[Scenario] = []
        for i in range(n):
            strategy = MUTATION_STRATEGIES[i % len(MUTATION_STRATEGIES)]
            base = _base_happy_path(
                scenario_id=f"scn-gen-{uuid.uuid4().hex[:8]}",
                city="Austin",
            )
            base.metadata["task_id"] = task.task_id
            mutated = self.mutate(base, strategy, mock_llm=mock_llm)
            scenarios.append(mutated)
        return scenarios

    def mutate(
        self,
        scenario: Scenario,
        strategy: str,
        *,
        mock_llm: bool = False,
    ) -> Scenario:
        """Apply a named mutation strategy to a base scenario."""
        normalized = strategy.strip().lower()
        if normalized not in MUTATION_STRATEGIES:
            raise ValueError(
                f"Unknown mutation strategy {strategy!r}; "
                f"expected one of {list(MUTATION_STRATEGIES)}"
            )
        typed_strategy: MutationStrategy = normalized  # type: ignore[assignment]

        if mock_llm:
            tool_responses = _mock_mutation_payloads(typed_strategy)
        else:
            tool_responses = self._llm_mutate(scenario, typed_strategy)

        return Scenario(
            scenario_id=f"scn-{typed_strategy.replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
            tool_responses=tool_responses,
            environment_config=dict(scenario.environment_config),
            metadata={
                **dict(scenario.metadata),
                "mutation_strategy": typed_strategy,
                "parent_scenario_id": scenario.scenario_id,
            },
        )

    def _llm_mutate(
        self,
        scenario: Scenario,
        strategy: MutationStrategy,
    ) -> list[ToolResponse]:
        prompt = (
            "You generate adversarial hotel-booking tool responses.\n"
            f"Mutation strategy: {strategy}\n"
            "Strategies mean:\n"
            '- "partial success": confirm_booking returns status pending (partial).\n'
            '- "silent failure": response looks ok=true but booking is not truly confirmed '
            "(e.g. status pending, no confirmation_id).\n"
            '- "missing information": omit confirmation_id even if status says confirmed.\n'
            '- "delayed failure": early tools succeed; confirm_booking fails with timeout/error.\n'
            "Return ONLY a JSON object with key tool_responses: a list of objects each with "
            "tool_name, call_index, response (object), response_type "
            "(success|partial|error|timeout|malformed).\n"
            "Include search_hotels, request_booking, and confirm_booking in that order.\n"
            f"Base scenario JSON:\n{scenario.model_dump_json()}"
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.rate_limiter.wait()
            try:
                completion = groq_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": "You output strict JSON only. No markdown.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                text = completion.choices[0].message.content or "{}"
                return _parse_tool_responses(text)
            except Exception as exc:  # noqa: BLE001 - retry free-tier / parse errors
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self.rate_limiter.backoff(attempt)

        assert last_error is not None
        raise last_error


def _parse_tool_responses(text: str) -> list[ToolResponse]:
    payload = _extract_json_object(text)
    raw_items = payload.get("tool_responses")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("LLM did not return tool_responses list")

    parsed: list[ToolResponse] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        response_type = item.get("response_type", "success")
        if response_type not in {"success", "partial", "error", "timeout", "malformed"}:
            response_type = "partial"
        parsed.append(
            ToolResponse(
                tool_name=str(item.get("tool_name", "unknown")),
                call_index=int(item.get("call_index", 0)),
                response=dict(item.get("response") or {}),
                response_type=response_type,
            )
        )
    if not parsed:
        raise ValueError("No valid tool responses parsed from LLM output")
    return parsed


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON payload was not an object")
    return data
