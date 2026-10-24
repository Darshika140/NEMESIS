"""Build deterministic compliance records from persisted claim-diff evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from nemesis.api.schemas import AuditEntry, AuditRequest, AuditTrailResponse


def audit_claims(request: AuditRequest) -> AuditTrailResponse:
    """Record unsupported claims without asking another model to interpret them."""
    timestamp = datetime.now(timezone.utc)
    audits = [
        AuditEntry(
            model_version="not_recorded",
            timestamp=timestamp,
            isolated_claim=claim.original,
            divergence_reason=(
                f"Claim is unsupported by the recorded baseline. "
                f"Expected: {claim.expected} Verified response: {claim.fixed}"
            ),
        )
        for claim in request.scenario.claim_diff
        if claim.status == "unsupported"
    ]
    return AuditTrailResponse(audits=audits)
