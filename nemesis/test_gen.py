"""Generate executable pytest regression tests from minimized scenarios."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from nemesis.minimizer import MinimizedScenario
from nemesis.models import TaskRequirement


@dataclass
class RegressionTest:
    """An executable pytest module (as source text) derived from a failure."""

    name: str
    scenario_id: str
    source_code: str
    violation_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RegressionTestGenerator:
    """Turn minimized scenarios into standalone pytest regression tests."""

    def generate(
        self,
        minimized_scenario: MinimizedScenario,
        task: TaskRequirement,
        *,
        mock_llm: bool = True,
    ) -> RegressionTest:
        scenario = minimized_scenario.scenario
        violation = minimized_scenario.preserved_violation
        safe_id = re.sub(r"[^a-zA-Z0-9_]+", "_", scenario.scenario_id)
        test_name = f"test_regression_{safe_id}"

        scenario_payload = json.dumps(scenario.model_dump())
        scenario_embed = json.dumps(scenario_payload)
        expected_violation = json.dumps(violation)
        task_id_literal = json.dumps(task.task_id)

        source_code = f'''"""Auto-generated NEMESIS regression test (mock_llm only)."""

from __future__ import annotations

import json

from nemesis.agents.booking_v1 import BookingAgentV1
from nemesis.checker import RequirementChecker
from nemesis.models import Scenario
from nemesis.runner import AgentRunner
from nemesis.tasks.booking import BOOKING_TASK

SCENARIO_DATA = json.loads({scenario_embed})
EXPECTED_VIOLATION = {expected_violation}
TASK_ID = {task_id_literal}


def {test_name}() -> None:
    assert BOOKING_TASK.task_id == TASK_ID
    scenario = Scenario.model_validate(SCENARIO_DATA)
    runner = AgentRunner()
    checker = RequirementChecker()
    trace = runner.run(BookingAgentV1(), scenario, BOOKING_TASK, mock_llm=True)
    result = checker.check(trace, BOOKING_TASK, mock_llm=True)
    assert result.passed is False
    if EXPECTED_VIOLATION is not None:
        assert result.violation_type == EXPECTED_VIOLATION
'''

        return RegressionTest(
            name=test_name,
            scenario_id=scenario.scenario_id,
            source_code=source_code,
            violation_type=violation,
            metadata={
                "task_id": task.task_id,
                "mock_llm": mock_llm,
                "original_scenario_id": minimized_scenario.original_scenario_id,
                "minimized_size": minimized_scenario.minimized_size,
            },
        )

    def generate_all(
        self,
        minimized_scenarios: list[MinimizedScenario],
        task: TaskRequirement,
        *,
        mock_llm: bool = True,
    ) -> list[RegressionTest]:
        return [
            self.generate(item, task, mock_llm=mock_llm) for item in minimized_scenarios
        ]
