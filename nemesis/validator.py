"""Fix validation: confirm a patched agent resolves minimized failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nemesis.checker import CheckResult, RequirementChecker
from nemesis.minimizer import MinimizedScenario
from nemesis.models import TaskRequirement
from nemesis.runner import AgentRunner, SupportsAgentStep


@dataclass
class FixCaseResult:
    scenario_id: str
    original_passed: bool
    fixed_passed: bool
    original_violation: str | None
    fixed_violation: str | None
    resolved: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class FixReport:
    """Summary of running minimized failures against original vs fixed agents."""

    total_failures: int
    original_still_fails: int
    fixed_passes: int
    resolved_count: int
    unresolved_count: int
    cases: list[FixCaseResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def all_resolved(self) -> bool:
        return self.total_failures > 0 and self.unresolved_count == 0


class FixValidator:
    """Re-run minimized failures on original and fixed agents."""

    def __init__(
        self,
        *,
        runner: AgentRunner | None = None,
        checker: RequirementChecker | None = None,
    ) -> None:
        self.runner = runner or AgentRunner(requests_per_minute=30.0)
        self.checker = checker or RequirementChecker()

    def validate(
        self,
        original_agent: SupportsAgentStep,
        fixed_agent: SupportsAgentStep,
        failures: list[MinimizedScenario],
        task: TaskRequirement,
        *,
        mock_llm: bool = True,
    ) -> FixReport:
        """Verify ``original_agent`` still fails and ``fixed_agent`` resolves each case.

        For ``false_success_claim`` failures, the fixed agent "passes" when it no longer
        makes a false success claim (even if invariants still fail because the world
        never reached a true confirmation). For other violations, require ``check.passed``.
        """
        cases: list[FixCaseResult] = []
        original_still_fails = 0
        fixed_passes = 0
        resolved = 0

        for failure in failures:
            scenario = failure.scenario

            original_agent.reset()
            orig_trace = self.runner.run(
                original_agent, scenario, task, mock_llm=mock_llm
            )
            orig_check = self.checker.check(orig_trace, task, mock_llm=mock_llm)

            fixed_agent.reset()
            fixed_trace = self.runner.run(
                fixed_agent, scenario, task, mock_llm=mock_llm
            )
            fixed_check = self.checker.check(fixed_trace, task, mock_llm=mock_llm)

            orig_fails = self._is_failure(orig_check, orig_trace, task)
            fixed_ok = self._is_fixed(
                orig_check,
                fixed_check,
                fixed_trace,
                task,
            )
            case_resolved = orig_fails and fixed_ok

            if orig_fails:
                original_still_fails += 1
            if fixed_ok:
                fixed_passes += 1
            if case_resolved:
                resolved += 1

            cases.append(
                FixCaseResult(
                    scenario_id=scenario.scenario_id,
                    original_passed=orig_check.passed,
                    fixed_passed=fixed_check.passed,
                    original_violation=orig_check.violation_type,
                    fixed_violation=fixed_check.violation_type,
                    resolved=case_resolved,
                    details={
                        "original_claimed_success": orig_trace.claimed_success,
                        "fixed_claimed_success": fixed_trace.claimed_success,
                        "world_status": fixed_trace.world_state.status,
                        "original_final_output": orig_trace.final_output,
                        "fixed_final_output": fixed_trace.final_output,
                    },
                )
            )

        return FixReport(
            total_failures=len(failures),
            original_still_fails=original_still_fails,
            fixed_passes=fixed_passes,
            resolved_count=resolved,
            unresolved_count=len(failures) - resolved,
            cases=cases,
            metadata={"mock_llm": mock_llm, "task_id": task.task_id},
        )

    @staticmethod
    def _is_failure(check: CheckResult, trace: Any, task: TaskRequirement) -> bool:
        if not check.passed:
            return True
        return bool(trace.claimed_success) and not bool(task.success_condition(trace))

    @staticmethod
    def _is_fixed(
        original_check: CheckResult,
        fixed_check: CheckResult,
        fixed_trace: Any,
        task: TaskRequirement,
    ) -> bool:
        # Primary bug class for booking_v1 → booking_v2.
        if original_check.violation_type == "false_success_claim":
            false_claim = bool(fixed_trace.claimed_success) and not bool(
                task.success_condition(fixed_trace)
            )
            return (
                fixed_check.violation_type != "false_success_claim"
                and not false_claim
            )
        return bool(fixed_check.passed)
