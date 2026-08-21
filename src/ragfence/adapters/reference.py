"""Database-backed reference adapter used by the production evaluation path."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.attacks.generators import EvaluationControl
from ragfence.auth.db import DbDirectory, DbIdentityProvider
from ragfence.auth.errors import IdentityNotFoundError
from ragfence.core.models import (
    AuthorizationContext,
    DocumentPolicy,
    RetrievalRequest,
    RetrievedChunk,
)
from ragfence.core.protocols import VectorStore
from ragfence.datasets.acme import build_acme_corp
from ragfence.db.models import Document, DocumentACL
from ragfence.db.vector_store import DbVectorStore
from ragfence.policies.guard import DocumentRowState
from ragfence.retrieval.result import SecureRetrievalResult
from ragfence.retrieval.service import RetrievalService


class ReferenceAdapter:
    """Evaluate persisted fixture identities through the production retrieval stack."""

    name = "reference"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.last_result: SecureRetrievalResult | None = None

    def materialize_precondition(self, control: EvaluationControl) -> Callable[[], None]:
        """Materialize preconditions for special controls (e.g., soft-deletion).

        For soft-deletion controls, soft-delete the target document before execution
        and restore it after. Returns a cleanup callable.
        """
        if control.category != "soft-deletion":
            return lambda: None

        acme = build_acme_corp()
        if control.target_document not in acme.documents:
            raise ValueError(f"target document not found: {control.target_document}")

        document_id = acme.documents[control.target_document].id

        with Session(self._engine) as session:
            doc = session.scalar(select(Document).where(Document.id == document_id))
            if doc is None:
                raise ValueError(f"document not found: {document_id}")
            if doc.deleted_at is not None:
                return lambda: None
            captured_deleted_at = datetime.now(UTC)
            session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(deleted_at=captured_deleted_at)
            )
            session.commit()

        def cleanup() -> None:
            with Session(self._engine) as session:
                stmt = (
                    update(Document)
                    .where(
                        Document.id == document_id,
                        Document.deleted_at == captured_deleted_at,
                    )
                    .values(deleted_at=None)
                )
                result = session.execute(stmt)
                if result.rowcount == 0:  # type: ignore[attr-defined]
                    raise RuntimeError(
                        f"document {document_id} was externally modified during precondition window"
                    )
                session.commit()

        return cleanup

    def _authorization(self, supplied: AuthorizationContext) -> AuthorizationContext:
        with Session(self._engine) as session:
            provider = DbIdentityProvider(session, supplied.tenant_id)
            identity = provider.resolve_user_id(supplied.user_id)
            if identity.tenant_id != supplied.tenant_id:
                raise IdentityNotFoundError(str(supplied.user_id))
            return DbDirectory(session).lookup(identity)

    def retrieve(self, request: RetrievalRequest) -> SecureRetrievalResult:
        """Run persisted authorization and pgvector retrieval without a test double."""
        authorization = self._authorization(request.authorization)

        def load_row(document_id: UUID) -> DocumentRowState | None:
            with Session(self._engine) as session:
                document = session.scalar(select(Document).where(Document.id == document_id))
                if document is None:
                    return None
                return DocumentRowState(
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    status=document.status,
                    deleted_at=document.deleted_at,
                )

        def policy(document_id: UUID) -> DocumentPolicy:
            with Session(self._engine) as session:
                acl = session.scalar(
                    select(DocumentACL).where(DocumentACL.document_id == document_id)
                )
                if acl is None:
                    raise KeyError(f"document ACL not found: {document_id}")
                return DocumentPolicy(
                    classification=acl.classification,
                    department_id=acl.department_id,
                    allowed_user_ids=set(acl.allowed_user_ids),
                    allowed_group_ids=set(acl.allowed_group_ids),
                )

        def document_meta(document_id: UUID) -> Document | None:
            with Session(self._engine) as session:
                return session.scalar(select(Document).where(Document.id == document_id))

        service = RetrievalService(
            store=cast(VectorStore, DbVectorStore(self._engine)),
            load_row=load_row,
            policy=policy,
            document_meta=document_meta,
        )
        result = service.retrieve(request.model_copy(update={"authorization": authorization}))
        self.last_result = result
        return result

    def answer(self, request: RetrievalRequest, chunks: list[RetrievedChunk]) -> str:
        """Return deterministic fake generation from authorized context only."""
        del request
        if not chunks:
            return "blocked"
        return "\n".join(chunk.content for chunk in chunks)

    def is_healthy(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
