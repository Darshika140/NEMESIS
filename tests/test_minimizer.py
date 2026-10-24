"""Tests for scenario minimization and regression test generation (mock_llm)."""

from __future__ import annotations

from nemesis.agents.booking_v1 import AgentAction, BookingAgentV1
from nemesis.checker import RequirementChecker
from nemesis.generator import ScenarioGenerator
from nemesis.minimizer import Minimizer
from nemesis.models import Scenario, ToolResponse
from nemesis.runner import AgentRunner
from nemesis.tasks.booking import BOOKING_TASK, DEMO_HOTELS
from nemesis.test_gen import RegressionTestGenerator


class _MockPendingAgent:
    """Minimal mock agent that reproduces the pending→false-success bug."""

    def __init__(self) -> None:
        self._phase = 0

    def reset(self) -> None:
        self._phase = 0

    def initial_messages(self, task_description: str, city: str = "Austin"):
        return [
            {"role": "system", "content": "mock"},
            {"role": "user", "content": f"{task_description} in {city}."},
        ]

    def step(self, messages, *, mock_llm: bool = False) -> AgentAction:
        phase = self._phase
        self._phase += 1
        if phase == 0:
            return AgentAction(
                thought="search",
                tool_call={"name": "search_hotels", "arguments": {"city": "Austin"}},
            )
        if phase == 1:
            return AgentAction(
                thought="request",
                tool_call={
                    "name": "request_booking",
                    "arguments": {"hotel_id": "HTL-001"},
                },
            )
        if phase == 2:
            return AgentAction(
                thought="confirm",
                tool_call={
                    "name": "confirm_booking",
                    "arguments": {"booking_id": "BKG-1001"},
                },
            )
        # Flawed: claim success after confirm regardless of pending.
        return AgentAction(
            thought="done",
            final_output="Your booking is confirmed!",
            claimed_success=True,
        )


def _pending_scenario() -> Scenario:
    hotels = [dict(h) for h in DEMO_HOTELS]
    return Scenario(
        scenario_id="scn-min-test-pending",
        tool_responses=[
            ToolResponse(
                tool_name="search_hotels",
                call_index=0,
                response={"hotels": hotels, "city": "Austin"},
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
                    "status": "pending",
                },
                response_type="partial",
            ),
            # Extra decoy response that should be removable if unused.
            ToolResponse(
                tool_name="check_booking_status",
                call_index=0,
                response={"status": "pending"},
                response_type="success",
            ),
        ],
        environment_config={"city": "Austin"},
        metadata={"case": "minimizer"},
    )


def test_minimizer_produces_1_minimal_reproducer() -> None:
    scenario = _pending_scenario()
    agent = _MockPendingAgent()
    runner = AgentRunner()
    checker = RequirementChecker()

    trace = runner.run(agent, scenario, BOOKING_TASK, mock_llm=True)
    check = checker.check(trace, BOOKING_TASK, mock_llm=True)
    assert check.passed is False
    assert check.violation_type == "false_success_claim"

    minimizer = Minimizer(agent=agent, checker=checker)
    minimized = minimizer.minimize(
        scenario,
        trace,
        BOOKING_TASK,
        runner,
        agent=agent,
        mock_llm=True,
    )

    assert minimized.minimized_size <= minimized.original_size
    assert minimized.minimized_size >= 1
    assert minimized.preserved_violation == "false_success_claim"
    assert minimized.scenario.metadata.get("minimized") is True

    # 1-minimal: dropping any remaining response should lose the violation.
    for index in range(len(minimized.tool_responses)):
        trial_responses = [
            item for i, item in enumerate(minimized.tool_responses) if i != index
        ]
        if not trial_responses:
            continue
        trial = Scenario(
            scenario_id="scn-trial",
            tool_responses=trial_responses,
            environment_config=dict(minimized.scenario.environment_config),
        )
        agent.reset()
        trial_trace = runner.run(agent, trial, BOOKING_TASK, mock_llm=True)
        trial_check = checker.check(trial_trace, BOOKING_TASK, mock_llm=True)
        assert (
            trial_check.violation_type != "false_success_claim"
            or trial_check.passed
        )


def test_minimizer_with_booking_v1_and_test_gen() -> None:
    generator = ScenarioGenerator()
    scenarios = generator.generate(BOOKING_TASK, n=1, mock_llm=True)
    scenario = scenarios[0]  # partial success → pending

    agent = BookingAgentV1()
    runner = AgentRunner()
    checker = RequirementChecker()
    trace = runner.run(agent, scenario, BOOKING_TASK, mock_llm=True)
    check = checker.check(trace, BOOKING_TASK, mock_llm=True)
    assert check.violation_type == "false_success_claim"

    minimized = Minimizer(agent=agent).minimize(
        scenario, trace, BOOKING_TASK, runner, mock_llm=True
    )
    regression = RegressionTestGenerator().generate(minimized, BOOKING_TASK, mock_llm=True)

    assert regression.name.startswith("test_regression_")
    assert "BookingAgentV1" in regression.source_code
    assert "mock_llm=True" in regression.source_code
    assert regression.violation_type == "false_success_claim"
    # Source must be syntactically valid Python.
    compile(regression.source_code, "<regression>", "exec")
    namespace = {}
    exec(regression.source_code, namespace)
    namespace[regression.name]()
