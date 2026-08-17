"""Canonical domain models (TRD §3.1-§3.5, §7).

Pure data containers: no I/O, no ORM, no network. Sets serialize to JSON
arrays and normalize back to ``set[UUID]`` on round-trip (JSONB contract).
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ragfence.core.enums import Classification, FindingSeverity


class AuthorizationContext(BaseModel):
    """Server-derived identity used for access decisions (TRD §3.2)."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    user_id: UUID
    department_id: UUID | None
    classification: Classification
    allowed_user_ids: set[UUID]
    allowed_group_ids: set[UUID]
    is_authenticated: bool
    source: Literal["synthetic", "oidc", "api_token"]


class DocumentACL(BaseModel):
    """Persisted ACL shape (DB row) for a document (TRD §3.2)."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    tenant_id: UUID
    department_id: UUID | None
    classification: Classification
    allowed_user_ids: set[UUID]
    allowed_group_ids: set[UUID]


class DocumentPolicy(BaseModel):
    """Declarative access rule: department scope with optional allowlists (TRD §3.2)."""

    model_config = ConfigDict(extra="forbid")

    classification: Classification
    department_id: UUID | None
    allowed_user_ids: set[UUID]
    allowed_group_ids: set[UUID]


class PolicyDecision(BaseModel):
    """Outcome of the policy engine (TRD §3.2); ``reasons`` name failing rules."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reasons: list[str]
    evaluated_at: datetime


class RetrievalRequest(BaseModel):
    """Normalized retrieval input; filters are server-derived only (TRD §3.3)."""

    model_config = ConfigDict(extra="forbid")

    query: str
    authorization: AuthorizationContext
    top_k: int = 10
    filters: dict[str, Any] = {}


class RetrievedChunk(BaseModel):
    """A retrieved passage with evidence metadata (TRD §3.3)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    document_title: str
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any]


class Citation(BaseModel):
    """Reference to an allowed document in a generated answer (TRD §3.3).

    ``source``/``checksum``/``score`` are provenance fields added for the
    secure-retrieval path (Phase 5); they are optional so existing constructions
    that only carry ``document_id``/``document_title``/``chunk_index``/``snippet``
    remain valid.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    document_title: str
    chunk_index: int
    snippet: str
    source: str | None = None
    checksum: str | None = None
    score: float | None = None


class AttackScenario(BaseModel):
    """Declarative adversarial scenario definition (TRD §3.5)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    target_stage: Literal["retrieval", "generation", "both"]
    expected_behavior: Literal["must_block", "must_allow"]


class EvaluationCase(BaseModel):
    """A concrete case instantiated from an AttackScenario (TRD §3.5)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    scenario_id: str
    prompt: str
    actor: AuthorizationContext
    expected_allow: bool


class SecurityFinding(BaseModel):
    """A structured finding produced by the evaluation engine (TRD §3.5)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    severity: FindingSeverity
    category: str
    title: str
    description: str
    evidence: dict[str, Any]


class EvaluationResult(BaseModel):
    """Per-case evaluation outcome (TRD §3.5)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    case_id: UUID
    passed: bool
    findings: list[SecurityFinding]
    retrieved: list[RetrievedChunk]
    answer: str | None
    latency_ms: int


class Message(BaseModel):
    """Chat message exchanged with an LLM provider (TRD §7)."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    """Completion result from an LLM provider (TRD §7)."""

    model_config = ConfigDict(extra="forbid")

    content: str
    prompt_tokens: int
    completion_tokens: int
