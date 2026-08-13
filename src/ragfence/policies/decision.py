"""Pure policy decision engine (TRD §5.3 rules 4-9).

Deterministic and I/O-free. Row-state rules (1-3: deleted_at, status, tenant)
are enforced by the storage layer / retrieval guard before this runs.
"""

from datetime import UTC, datetime

from ragfence.core.models import AuthorizationContext, DocumentPolicy, PolicyDecision

REASON_CLASSIFICATION_ESCALATION = "classification_escalation"
REASON_NO_IMPLICIT_DEPARTMENT_ACCESS = "no_implicit_department_access"
REASON_DENY_BY_DEFAULT = "deny_by_default"


def decide(policy: DocumentPolicy, ctx: AuthorizationContext) -> PolicyDecision:
    """Evaluate TRD §5.3 rules 4-9 and return a deterministic PolicyDecision.

    Rule order: classification escalation (4) first; explicit grants (5-6)
    precede department scoping (7-8); everything else denies (9).
    """
    evaluated_at = datetime.now(UTC)

    if policy.classification.rank > ctx.classification.rank:
        return PolicyDecision(
            allowed=False, reasons=[REASON_CLASSIFICATION_ESCALATION], evaluated_at=evaluated_at
        )
    if ctx.user_id in policy.allowed_user_ids:
        return PolicyDecision(allowed=True, reasons=[], evaluated_at=evaluated_at)
    if ctx.allowed_group_ids.intersection(policy.allowed_group_ids):
        return PolicyDecision(allowed=True, reasons=[], evaluated_at=evaluated_at)
    if policy.department_id is None:
        return PolicyDecision(
            allowed=False, reasons=[REASON_NO_IMPLICIT_DEPARTMENT_ACCESS], evaluated_at=evaluated_at
        )
    if policy.department_id == ctx.department_id:
        return PolicyDecision(allowed=True, reasons=[], evaluated_at=evaluated_at)
    return PolicyDecision(
        allowed=False, reasons=[REASON_DENY_BY_DEFAULT], evaluated_at=evaluated_at
    )
