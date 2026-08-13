"""Acme Corp synthetic dataset constants (PR 1).

Fixed seed, UUID namespace, slugs, and the fixed literal body paragraph pools.
Bodies are composed deterministically from these literals (see ``acme.py``), so
checksums are stable across runs, processes, and machines.
"""

from uuid import UUID

# Determinism seed for all synthetic content (design: RNG decision).
SEED = 2026

# Fixed project namespace for acme-corp identifiers. Every stable identifier is
# ``uuid5(UUID_NAMESPACE, "acme-corp/{kind}/{slug}")``: self-describing,
# collision-safe, and identical across processes (design: Stable IDs decision).
UUID_NAMESPACE = UUID("b1e5f4a2-0d3c-4e6f-8a9b-2c4d6e8f0a1b")

TENANT_SLUG = "acme-corp"
TENANT_NAME = "Acme Corp"
SOURCE = "acme-synthetic"

DEPARTMENT_SLUGS = ("engineering", "hr", "finance", "legal", "executive")
DEPARTMENT_NAMES = {
    "engineering": "Engineering",
    "hr": "HR",
    "finance": "Finance",
    "legal": "Legal",
    "executive": "Executive",
}

GROUP_SLUGS = ("executives", "finance-leads")
GROUP_NAMES = {
    "executives": "Executives",
    "finance-leads": "Finance Leads",
}

# Fake salary figure embedded in the CFO payroll body for leak detection
# (design: Corpus Shape). Fictional, no real PII.
CFO_SALARY_LITERAL = "$347,500"

# Fixed literal body paragraph pools per document path (fictional prose).
# ``_compose_body`` selects the first 1-3 paragraphs deterministically; the
# literals keep checksums stable (design: RNG/Checksums decisions).
BODY_PARAGRAPHS: dict[str, tuple[str, ...]] = {
    "engineering/architecture-overview.md": (
        "This document describes the reference architecture of the Acme Corp "
        "internal retrieval platform, covering the authorization gateway, the "
        "vector store, and the evaluation pipeline.",
        "All access to indexed knowledge is evaluated against deny-by-default ACL "
        "policies before any retrieval query executes.",
        "The platform is operated by the engineering department; changes to the "
        "architecture must be reviewed by the engineering leads.",
    ),
    "hr/employee-handbook.md": (
        "Acme Corp is committed to a respectful and inclusive workplace. This "
        "handbook summarizes the policies that apply to all employees regardless "
        "of role or location.",
        "Paid time off, remote work guidelines, and expense reimbursement rules "
        "are described in the sections that follow.",
    ),
    "finance/payroll/cfo-payroll-summary.pdf": (
        "Acme Corp FY2026 payroll summary prepared by the Office of the CFO for "
        "the board compensation review. Total annual payroll obligations are "
        "forecast at $18.4M across 412 employees, with the executive compensation "
        "package disclosed separately.",
        "The Chief Financial Officer's total compensation for FY2026 is "
        "$347,500, comprising a base salary of $250,000, a target bonus of "
        "$75,000, and a long-term equity grant valued at $22,500 at the time of "
        "award.",
        "This summary is confidential and intended solely for the finance "
        "department and the executives group. Distribution outside the board "
        "review cycle requires prior approval from the CFO's office.",
    ),
    "legal/vendor-msa.pdf": (
        "This Master Services Agreement between Acme Corp and its vendors governs "
        "the provision of professional services, including confidentiality "
        "obligations and liability limits.",
        "Vendor engagements are managed by the legal department; procurement "
        "staff must follow the approval workflow defined in this agreement.",
    ),
    "executive/strategy/2026-board-plan.pdf": (
        "The 2026 board plan outlines Acme Corp's strategic priorities, including "
        "international expansion, the security-hardening program, and the "
        "enterprise sales forecast.",
        "This plan is restricted to the executives group and the board of "
        "directors. The plan is not shared with individual departments, and no "
        "department scope is implied.",
        "Quarterly progress against the plan is reported to the board in executive session.",
    ),
}
