"""TDD contracts for the EvaluationEngine persistence seam (G2-G4)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import pytest

from ragfence.evaluation.engine import EvaluationEngine


class _Target:
    def retrieve(self, request: Any) -> list[Any]:
        return []

    def answer(self, request: Any, chunks: list[Any]) -> str:
        return "safe"


class _Session:
    """Minimal transaction probe; repository methods are replaced at the seam."""

    def __init__(self) -> None:
        self.begin_count = 0
        self.rollback_count = 0

    def begin(self) -> Any:
        session = self

        class Transaction:
            def __enter__(self) -> Any:
                session.begin_count += 1
                return session

            def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
                return False

        return Transaction()

    def rollback(self) -> None:
        self.rollback_count += 1


def test_engine_persists_complete_summary_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session: Any = _Session()
    summary = EvaluationEngine(_Target(), seed=11).run()
    calls: list[str] = []

    class Repository:
        def upsert_suite(self, **kwargs: Any) -> Any:
            calls.append("suite")
            return type("Suite", (), {"id": UUID("11111111-1111-4111-8111-111111111111")})()

        def upsert_case(self, **kwargs: Any) -> Any:
            calls.append("case")
            return type("Case", (), {"id": kwargs["case_id"]})()

        def upsert_run(self, **kwargs: Any) -> Any:
            calls.append("run")
            return type("Run", (), {"id": kwargs["run_id"]})()

        def upsert_result(self, **kwargs: Any) -> Any:
            calls.append("result")
            return object()

        def reconcile_findings(self, **kwargs: Any) -> list[Any]:
            calls.append("findings")
            return []

    monkeypatch.setattr("ragfence.evaluation.engine.EvaluationRepository", lambda _: Repository())

    persisted = EvaluationEngine(_Target(), seed=11).persist(summary, session)

    assert persisted.run_id
    assert calls[0] == "suite"
    assert calls.count("case") == len(summary.results)
    assert calls.count("result") == len(summary.results)
    assert calls[-1] == "findings"
    assert session.begin_count == 1
    assert session.rollback_count == 0


def test_engine_rolls_back_when_persistence_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    session: Any = _Session()
    summary = EvaluationEngine(_Target(), seed=12).run()

    class Repository:
        def upsert_suite(self, **kwargs: Any) -> Any:
            raise RuntimeError("write failed")

    monkeypatch.setattr("ragfence.evaluation.engine.EvaluationRepository", lambda _: Repository())

    with pytest.raises(RuntimeError, match="write failed"):
        EvaluationEngine(_Target(), seed=12).persist(summary, session)

    assert session.rollback_count == 1


def test_replay_uses_same_run_identity_and_canonical_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    session: Any = _Session()
    summary = EvaluationEngine(_Target(), seed=13).run()
    run_ids: list[UUID] = []

    class Repository:
        def upsert_suite(self, **kwargs: Any) -> Any:
            return type("Suite", (), {"id": UUID("11111111-1111-4111-8111-111111111111")})()

        def upsert_case(self, **kwargs: Any) -> Any:
            return type("Case", (), {"id": kwargs["case_id"]})()

        def upsert_run(self, **kwargs: Any) -> Any:
            run_ids.append(kwargs["run_id"])
            return type("Run", (), {"id": kwargs["run_id"]})()

        def upsert_result(self, **kwargs: Any) -> Any:
            return object()

        def reconcile_findings(self, **kwargs: Any) -> list[Any]:
            return []

    monkeypatch.setattr("ragfence.evaluation.engine.EvaluationRepository", lambda _: Repository())
    engine = EvaluationEngine(_Target(), seed=13)
    first = engine.replay(summary, session)
    second = engine.replay(summary, session)

    assert first.run_id == second.run_id
    assert run_ids == [first.run_id, second.run_id]
    assert summary.canonical_bytes() == summary.canonical_bytes()
