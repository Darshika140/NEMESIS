"""Flawed ReAct hotel-booking agent (booking_v1) using Groq via litellm.

Deliberate bug: after ``confirm_booking`` returns ``status="pending"``, the agent
treats the booking as successful and reports confirmation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from nemesis.runner import DEFAULT_GROQ_MODEL, groq_completion

BOOKING_V1_MODEL = DEFAULT_GROQ_MODEL

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search for hotels in a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City to search"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_booking",
            "description": "Request a booking for a hotel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hotel_id": {"type": "string"},
                },
                "required": ["hotel_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_booking",
            "description": "Confirm a previously requested booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "string"},
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_booking_status",
            "description": "Check the current booking status.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a hotel booking assistant. Use the available tools to search for "
    "hotels, request a booking, and confirm it. Prefer Harbor Inn (HTL-001) when "
    "multiple hotels are available. When the booking appears done, tell the user "
    "clearly. Reply with a short final message and do not call tools after you are done."
)

CONFIRMED_MESSAGE = "Your booking is confirmed!"


@dataclass
class AgentAction:
    """One decision from the agent: either a tool call or a final answer."""

    thought: str | None = None
    tool_call: dict[str, Any] | None = None
    final_output: str | None = None
    claimed_success: bool | None = None


class BookingAgentV1:
    """ReAct-style booking agent with a planted pending-as-success flaw."""

    name = "booking_v1"
    model = BOOKING_V1_MODEL

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
        """Return the next tool call or final answer given the conversation so far."""
        flawed = self._flawed_success_if_pending(messages)
        if flawed is not None:
            return flawed

        if mock_llm:
            return self._mock_step(messages)
        return self._llm_step(messages)

    def _flawed_success_if_pending(
        self,
        messages: list[dict[str, Any]],
    ) -> AgentAction | None:
        """Planted bug: treat confirm_booking status=pending as confirmed success."""
        last_tool = _last_tool_result(messages)
        if last_tool is None:
            return None
        name, payload = last_tool
        if name != "confirm_booking":
            return None
        status = payload.get("status")
        # Flaw: pending is incorrectly treated as success (confirmed is also accepted).
        if status in {"pending", "confirmed"}:
            return AgentAction(
                thought=(
                    "confirm_booking returned a status; treating the booking as done."
                    if status == "pending"
                    else "confirm_booking returned confirmed."
                ),
                final_output=CONFIRMED_MESSAGE,
                claimed_success=True,
            )
        return None

    def _mock_step(self, messages: list[dict[str, Any]]) -> AgentAction:
        """Deterministic offline policy used when ``mock_llm=True``."""
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
        claimed = "confirmed" in text.lower()
        return AgentAction(
            thought=thought,
            final_output=text,
            claimed_success=claimed,
        )


def _last_tool_result(
    messages: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        name = message.get("name") or ""
        content = message.get("content", {})
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = {"raw": content}
        else:
            payload = dict(content)
        return name, payload
    return None


def _payload_from_tool(
    messages: list[dict[str, Any]],
    tool_name: str,
) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "tool" and message.get("name") == tool_name:
            content = message.get("content", {})
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
            return dict(content)
    return {}


def _extract_city(messages: list[dict[str, Any]]) -> str | None:
    for message in messages:
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        marker = "in "
        if marker in content:
            # "... in Austin." → Austin
            tail = content.rsplit(marker, 1)[-1]
            return tail.strip().rstrip(".")
    return None
