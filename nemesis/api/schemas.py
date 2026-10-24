"""Typed JSON contracts for the dashboard API."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Metrics(BaseModel):
    scenarios_generated: int = 0
    failures_discovered: int = 0
    false_success_claims: int = 0
    scenarios_minimized: int = 0
    tests_generated: int = 0
    fixes_validated: int = 0
    fixes_resolved: int = 0


class FailureSummary(BaseModel):
    id: str
    title: str
    kind: str
    scenario: str
    status: str
    summary: str


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    mode: str
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    metrics: Metrics = Field(default_factory=Metrics)
    failures: list[FailureSummary] = Field(default_factory=list)


class LatestRunResponse(BaseModel):
    run: RunResponse | None


class ScenarioDetail(BaseModel):
    id: str
    title: str
    kind: str
    scenario: str
    status: str
    summary: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    mechanism: str = ""
    verification: dict[str, Any] = Field(default_factory=dict)
    regression_test: str | None = None
    claim_diff: list["ClaimDiff"] = Field(default_factory=list)


class ClaimDiff(BaseModel):
    status: Literal["unsupported", "aligned", "changed"]
    original: str
    fixed: str
    expected: str


class ScenarioResponse(BaseModel):
    scenario: ScenarioDetail


class RunRequest(BaseModel):
    mode: Literal["live_llm", "local_llm", "mock_llm"] = "live_llm"
    n_scenarios: int = Field(default=4, ge=1, le=32)


class RunAcceptedResponse(BaseModel):
    run: RunResponse


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    execution_logs: dict[str, Any] = Field(default_factory=dict)
    provider: Literal["groq", "ollama"] = "groq"

    @field_validator("execution_logs")
    @classmethod
    def limit_execution_log_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("execution_logs must contain JSON-compatible data") from exc
        if len(encoded.encode("utf-8")) > 256_000:
            raise ValueError("execution_logs must not exceed 256 KB")
        return value


class ChatEvidence(BaseModel):
    path: str
    quote: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[ChatEvidence] = Field(default_factory=list)
    insufficient_data: bool = False
    provider: Literal["groq", "ollama"]
    model: str


class HealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=12000)
    failure_evidence: dict[str, Any]
    test_cases: list[str] = Field(min_length=1, max_length=20)
    provider: Literal["groq", "ollama"] = "groq"
    max_iterations: int = Field(default=3, ge=1, le=5)

    @field_validator("failure_evidence")
    @classmethod
    def limit_evidence_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("failure_evidence must contain JSON-compatible data") from exc
        if len(encoded.encode("utf-8")) > 128_000:
            raise ValueError("failure_evidence must not exceed 128 KB")
        return value

    @field_validator("test_cases")
    @classmethod
    def limit_test_case_size(cls, value: list[str]) -> list[str]:
        if any(len(test_case) > 4_000 for test_case in value):
            raise ValueError("each test case must not exceed 4,000 characters")
        if sum(len(test_case) for test_case in value) > 32_000:
            raise ValueError("combined test cases must not exceed 32,000 characters")
        return value


class HealIteration(BaseModel):
    iteration: int
    red_team_passed: bool
    finding: str
    counterexample: str | None = None
    fixer_model: str
    red_team_model: str


class HealResponse(BaseModel):
    verified: bool
    provider: Literal["groq", "ollama"]
    model: str
    iterations: list[HealIteration]
    original_instruction: str
    proposed_instruction: str
    message: str


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: ScenarioDetail

    @field_validator("scenario")
    @classmethod
    def limit_audit_scenario_size(cls, value: ScenarioDetail) -> ScenarioDetail:
        if len(value.model_dump_json().encode("utf-8")) > 128_000:
            raise ValueError("scenario must not exceed 128 KB")
        return value


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_version: str
    timestamp: datetime
    isolated_claim: str
    divergence_reason: str


class AuditTrailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audits: list[AuditEntry] = Field(default_factory=list)
