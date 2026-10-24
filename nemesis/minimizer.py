"""Scenario minimization via greedy 1-minimal step removal (delta debugging)."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

from nemesis.checker import RequirementChecker
from nemesis.models import AgentTrace, Scenario, TaskRequirement, ToolResponse
from nemesis.runner import AgentRunner, SupportsAgentStep


@dataclass
class MinimizedScenario:
    """Result of minimizing a failing scenario to a 1-minimal reproducer."""

    scenario: Scenario
    original_scenario_id: str
    original_size: int
    minimized_size: int
    preserved_violation: str | None
    trace: AgentTrace | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_responses(self) -> list[ToolResponse]:
        return self.scenario.tool_responses

    @property
    def scenario_id(self) -> str:
        return self.scenario.scenario_id


class Minimizer:
    """Greedy step-removal minimizer that preserves the same checker violation."""

    def __init__(
        self,
        *,
        agent: SupportsAgentStep | None = None,
        checker: RequirementChecker | None = None,
        requests_per_minute: float = 30.0,
    ) -> None:
        self.agent = agent
        self.checker = checker or RequirementChecker()
        self.requests_per_minute = requests_per_minute

    def minimize(
        self,
        scenario: Scenario,
        trace: AgentTrace,
        task: TaskRequirement,
        runner: AgentRunner,
        *,
        agent: SupportsAgentStep | None = None,
        mock_llm: bool = True,
    ) -> MinimizedScenario:
        """Shrink ``scenario`` until removing any single ToolResponse loses the failure.

        Re-runs the agent through ``runner`` and uses ``RequirementChecker`` to confirm
        the same violation still appears after each candidate removal.
        """
        active_agent = agent or self.agent
        if active_agent is None:
            raise ValueError("Minimizer.minimize requires an agent (ctor or keyword arg)")

        original_check = self.checker.check(trace, task, mock_llm=mock_llm)
        if original_check.passed:
            raise ValueError("Minimizer.minimize requires a failing trace")
        target_violation = original_check.violation_type
        original_size = len(scenario.tool_responses)

        # Prefer responses actually observed in the failing trace, else full scenario.
        seed_responses = self._responses_from_trace(trace) or list(scenario.tool_responses)
        current = Scenario(
            scenario_id=f"scn-min-{uuid.uuid4().hex[:8]}",
            tool_responses=[item.model_copy(deep=True) for item in seed_responses],
            environment_config=dict(scenario.environment_config),
            metadata={
                **dict(scenario.metadata),
                "minimized": True,
                "parent_scenario_id": scenario.scenario_id,
                "original_violation": target_violation,
            },
        )

        if not self._reproduces(
            current, task, runner, active_agent, target_violation, mock_llm=mock_llm
        ):
            # Fall back to the full original scenario if the trace slice does not reproduce.
            current = Scenario(
                scenario_id=current.scenario_id,
                tool_responses=[item.model_copy(deep=True) for item in scenario.tool_responses],
                environment_config=dict(scenario.environment_config),
                metadata=dict(current.metadata),
            )

        current = self._greedy_1_minimal(
            current,
            task,
            runner,
            active_agent,
            target_violation,
            mock_llm=mock_llm,
        )

        final_trace = runner.run(active_agent, current, task, mock_llm=mock_llm)
        final_check = self.checker.check(final_trace, task, mock_llm=mock_llm)

        return MinimizedScenario(
            scenario=current,
            original_scenario_id=scenario.scenario_id,
            original_size=original_size,
            minimized_size=len(current.tool_responses),
            preserved_violation=final_check.violation_type,
            trace=final_trace,
            metadata={
                "original_violation": target_violation,
                "check_passed": final_check.passed,
            },
        )

    def _greedy_1_minimal(
        self,
        scenario: Scenario,
        task: TaskRequirement,
        runner: AgentRunner,
        agent: SupportsAgentStep,
        target_violation: str | None,
        *,
        mock_llm: bool,
    ) -> Scenario:
        current = copy.deepcopy(scenario)
        changed = True
        while changed and current.tool_responses:
            changed = False
            for index in range(len(current.tool_responses) - 1, -1, -1):
                trial_responses = [
                    item for i, item in enumerate(current.tool_responses) if i != index
                ]
                trial = Scenario(
                    scenario_id=current.scenario_id,
                    tool_responses=trial_responses,
                    environment_config=dict(current.environment_config),
                    metadata=dict(current.metadata),
                )
                if self._reproduces(
                    trial, task, runner, agent, target_violation, mock_llm=mock_llm
                ):
                    current = trial
                    changed = True
                    break
        return current

    def _reproduces(
        self,
        scenario: Scenario,
        task: TaskRequirement,
        runner: AgentRunner,
        agent: SupportsAgentStep,
        target_violation: str | None,
        *,
        mock_llm: bool,
    ) -> bool:
        agent.reset()
        new_trace = runner.run(agent, scenario, task, mock_llm=mock_llm)
        check = self.checker.check(new_trace, task, mock_llm=mock_llm)
        if check.passed:
            return False
        if target_violation is None:
            return not check.passed
        return check.violation_type == target_violation

    @staticmethod
    def _responses_from_trace(trace: AgentTrace) -> list[ToolResponse]:
        collected: list[ToolResponse] = []
        for step in trace.steps:
            if step.tool_response is not None:
                collected.append(step.tool_response.model_copy(deep=True))
        return collected
