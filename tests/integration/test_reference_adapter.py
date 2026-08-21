"""Real pgvector reference-adapter integration tests."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.adapters.reference import ReferenceAdapter
from ragfence.attacks.generators import generate_cases
from ragfence.core.models import RetrievalRequest
from ragfence.datasets import build_acme_corp, seed_reference_corp
from ragfence.db.base import Base
from ragfence.db.models import DocumentChunk
from ragfence.providers.fakes import FakeEmbeddingProvider
from ragfence.retrieval.result import RetrievalDecision


def _embed(text_value: str) -> list[float]:
    return FakeEmbeddingProvider().embed([text_value])[0]


def _seed_with_embeddings(engine: Engine) -> None:
    table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    with engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        connection.commit()
    with Session(engine) as session:
        seed_reference_corp(session)
        for chunk in session.scalars(select(DocumentChunk)).all():
            chunk.embedding = _embed(chunk.content)
        session.commit()


def _request(case) -> RetrievalRequest:
    return RetrievalRequest(
        query=case.prompt,
        authorization=case.actor,
        top_k=case.retrieval_options.top_k,
        filters=case.retrieval_options.filters,
    )


def test_reference_adapter_blocks_persisted_globex_actor_before_pgvector_search(
    db_engine: Engine,
) -> None:
    _seed_with_embeddings(db_engine)
    case = next(case for case in generate_cases() if case.scenario_id == "cross-tenant-retrieval")
    adapter = ReferenceAdapter(db_engine)

    result = adapter.retrieve(_request(case))

    assert result.decision is RetrievalDecision.DENY
    assert result.reasons == ["cross_tenant"]
    assert result.chunks == []
    assert result.trace.store_call_count == 0


def test_reference_adapter_returns_allowed_acme_chunk_through_pgvector(db_engine: Engine) -> None:
    _seed_with_embeddings(db_engine)
    dataset = build_acme_corp()
    actor = dataset.context_for("finance_analyst@acme-corp.example")
    document = dataset.documents["finance/payroll/cfo-payroll-summary.pdf"]
    adapter = ReferenceAdapter(db_engine)
    request = RetrievalRequest(
        query="payroll summary",
        authorization=actor,
        top_k=1,
        filters={"document_id": document.id},
    )

    result = adapter.retrieve(request)

    assert result.decision is RetrievalDecision.ALLOW
    assert result.trace.store_call_count == 1
    assert [chunk.document_id for chunk in result.chunks] == [document.id]
