"""PostgreSQL-gated G2-G4 persistence tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.db.models import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    SecurityFinding,
)
from ragfence.evaluation.engine import EvaluationEngine
from ragfence.evaluation.report import build_report
from tests.integration.test_evaluation_e2e_db import LeakingTarget, _clean_schema


@pytest.mark.db
def test_engine_persistence_is_atomic_and_rolls_back_on_failure(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clean_schema(db_engine)
    summary = EvaluationEngine(LeakingTarget(), seed=91, threshold=80).run()
    original = EvaluationEngine.persist

    def failing_persist(self: Any, summary: Any, session: Any, **kwargs: Any) -> Any:
        """Force a repository write failure inside the real transaction seam."""
        from ragfence.evaluation.repositories import EvaluationRepository

        original_write = EvaluationRepository.upsert_result

        def fail_once(repository: Any, **values: Any) -> Any:
            monkeypatch.setattr(EvaluationRepository, "upsert_result", original_write)
            raise RuntimeError("injected persistence failure")

        monkeypatch.setattr(EvaluationRepository, "upsert_result", fail_once)
        return original(self, summary, session, **kwargs)

    monkeypatch.setattr(EvaluationEngine, "persist", failing_persist)
    with pytest.raises(RuntimeError, match="injected persistence failure"):
        with Session(db_engine) as session:
            EvaluationEngine(LeakingTarget(), seed=91).persist(summary, session)
            session.commit()

    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(EvaluationSuite)) == 0
        assert session.scalar(select(func.count()).select_from(EvaluationCase)) == 0
        assert session.scalar(select(func.count()).select_from(EvaluationRun)) == 0
        assert session.scalar(select(func.count()).select_from(EvaluationResult)) == 0
        assert session.scalar(select(func.count()).select_from(SecurityFinding)) == 0


@pytest.mark.db
def test_engine_replay_is_idempotent_and_reloadable(db_engine: Engine) -> None:
    _clean_schema(db_engine)
    engine = EvaluationEngine(LeakingTarget(), seed=92, threshold=80)
    summary = engine.run()
    with Session(db_engine) as session:
        first = engine.persist(summary, session)
    with Session(db_engine) as session:
        second = engine.replay(summary, session)
        loaded = engine.reload(session, second.run_id)
        assert first == second
        assert loaded.run.id == first.run_id
        assert len(loaded.results) == len(summary.results)
        assert loaded.findings
        assert loaded.run.score == Decimal(str(round(summary.score, 2)))

    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(EvaluationSuite)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationCase)) == 10
        assert session.scalar(select(func.count()).select_from(EvaluationRun)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationResult)) == 10
        assert session.scalar(select(func.count()).select_from(SecurityFinding)) == len(
            loaded.findings
        )

    assert (
        build_report(summary, summary.results).payload
        == build_report(summary, summary.results).payload
    )


@pytest.mark.db
def test_replay_report_bytes_are_stable(db_engine: Engine) -> None:
    _clean_schema(db_engine)
    engine = EvaluationEngine(LeakingTarget(), seed=93, threshold=80)
    summary = engine.run()
    first_bytes = summary.canonical_bytes()
    with Session(db_engine) as session:
        engine.persist(summary, session)
    with Session(db_engine) as session:
        engine.replay(summary, session)
    assert first_bytes == summary.canonical_bytes()
