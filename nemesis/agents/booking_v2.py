"""Fixed ReAct hotel-booking agent (booking_v2).

Correct behavior: never claim success from ``confirm_booking`` alone. Always call
``check_booking_status`` first, and only report confirmed when status is
``confirmed``.
"""

from __future__ import annotations

import json
from typing import Any

from nemesis.agents.booking_v1 import (
    AgentAction,
    CONFIRMED_MESSAGE,
    TOOL_SCHEMAS,
    _extract_city,
    _last_tool_result,
    _payload_from_tool,
)
from nemesis.runner import DEFAULT_GROQ_MODEL, groq_completion

BOOKING_V2_MODEL = DEFAULT_GROQ_MODEL

SYSTEM_PROMPT = (
    "You are a careful hotel booking assistant. Use tools to search, request, "
    "and confirm a booking. Prefer Harbor Inn (HTL-001) when available. "
    "CRITICAL: After confirm_booking, you MUST call check_booking_status before "
    "telling the user anything is confirmed. Only say the booking is confirmed "
    "if check_booking_status returns status \"confirmed\". If status is pending "
    "or anything else, report that honestly and do not claim success."
)

PENDING_MESSAGE = "Your booking is not confirmed yet (status: {status})."


class BookingAgentV2:
    """ReAct booking agent that verifies status before claiming success."""

    name = "booking_v2"
    model = BOOKING_V2_MODEL

    def __init__(self) -> None:
        self._mock_phase = 0

    def reset(self) -> None:
        self._mock_phase = 0

    def initial_messages(self, task_description: str, city: str = "Austin") -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{task_description}\n"
                    f"Please book a hotel in {city}."
                ),
            },
        ]

    def step(
        self,
        messages: list[dict[str, Any]],
        *,
        mock_llm: bool = False,
    ) -> AgentAction:
        gated = self._status_gate(messages)
        if gated is not None:
            return gated

        if mock_llm:
            return self._mock_step(messages)
        return self._llm_step(messages)

    def _status_gate(self, messages: list[dict[str, Any]]) -> AgentAction | None:
        """Enforce check_booking_status before any success claim."""
        last = _last_tool_result(messages)
        if last is None:
            return None
        name, payload = last

        if name == "confirm_booking":
            return AgentAction(
                thought="Must verify booking status before claiming success.",
                tool_call={"name": "check_booking_status", "arguments": {}},
            )

        if name == "check_booking_status":
            status = str(payload.get("status", "unknown"))
            if status == "confirmed":
                return AgentAction(
                    thought="Status verified as confirmed.",
                    final_output=CONFIRMED_MESSAGE,
                    claimed_success=True,
                )
            return AgentAction(
                thought=f"Status is {status}; not claiming success.",
                final_output=PENDING_MESSAGE.format(status=status),
                claimed_success=False,
            )

        return None

    def _mock_step(self, messages: list[dict[str, Any]]) -> AgentAction:
        phase = self._mock_phase
        self._mock_phase += 1

        if phase == 0:
            city = _extract_city(messages) or "Austin"
            return AgentAction(
                thought="Search for hotels first.",
                tool_call={"name": "search_hotels", "arguments": {"city": city}},
            )

        if phase == 1:
            hotels = _payload_from_tool(messages, "search_hotels").get("hotels") or []
            hotel_id = hotels[0]["hotel_id"] if hotels else "HTL-001"
            return AgentAction(
                thought=f"Request a booking for {hotel_id}.",
                tool_call={
                    "name": "request_booking",
                    "arguments": {"hotel_id": hotel_id},
                },
            )

        if phase == 2:
            booking = _payload_from_tool(messages, "request_booking")
            booking_id = booking.get("booking_id") or "BKG-1001"
            return AgentAction(
                thought="Confirm the booking.",
                tool_call={
                    "name": "confirm_booking",
                    "arguments": {"booking_id": booking_id},
                },
            )

        # Status gate normally handles post-confirm / post-check; fallback:
        return AgentAction(
            thought="No further tools needed.",
            final_output="Unable to complete the booking.",
            claimed_success=False,
        )

    def _llm_step(self, messages: list[dict[str, Any]]) -> AgentAction:
        response = groq_completion(
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        thought = getattr(message, "content", None)

        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            call = tool_calls[0]
            raw_args = call.function.arguments
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    arguments = {}
            else:
                arguments = dict(raw_args or {})
            return AgentAction(
                thought=thought,
                tool_call={"name": call.function.name, "arguments": arguments},
            )

        text = thought or "Done."
        # Never allow an LLM final answer to claim success without the status gate
        # having already approved it (gate runs first on each step).
        claimed = False
        return AgentAction(
            thought=thought,
            final_output=text,
            claimed_success=claimed,
        )
