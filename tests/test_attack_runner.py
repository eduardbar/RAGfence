"""Attack runner and objective verdict tests."""

from types import SimpleNamespace

from ragfence.attacks.generators import generate_cases
from ragfence.attacks.runner import MAX_TOP_K, ScenarioObservation, run_case
from ragfence.core.enums import DocumentStatus
from ragfence.datasets.acme import build_acme_corp
from ragfence.retrieval.service import RetrievalService


class EmptyTarget:
    def retrieve(self, request):
        return []

    def answer(self, request, chunks):
        return "blocked"


class LeakyTarget:
    def retrieve(self, request):
        case = generate_cases()[1]
        return [
            {
                "chunk_id": case.id,
                "document_id": case.id,
                "document_title": "unauthorized",
                "chunk_index": 0,
                "content": "secret",
                "score": 1.0,
                "metadata": {},
            }
        ]

    def answer(self, request, chunks):
        return "leaked"


class FailingTarget:
    def retrieve(self, request):
        raise RuntimeError("target down")

    def answer(self, request, chunks):
        return ""


class GenerationLeakTarget:
    def retrieve(self, request):
        return []

    def answer(self, request, chunks):
        return "SECRET LEAK"


class RetrievalServiceShapeTarget:
    def __init__(self):
        self.request = None

    def retrieve(self, request):
        self.request = request
        return []

    def answer(self, request, chunks):
        return "blocked"


class TooManyChunksTarget:
    def retrieve(self, request):
        case = generate_cases()[0]
        return [
            {
                "chunk_id": case.id,
                "document_id": case.id,
                "document_title": "unauthorized",
                "chunk_index": index,
                "content": "secret",
                "score": 1.0,
                "metadata": {},
            }
            for index in range(MAX_TOP_K + 1)
        ]

    def answer(self, request, chunks):
        return "blocked"


class AnswerFailsAfterRetrievalTarget:
    def retrieve(self, request):
        case = generate_cases()[0]
        return [
            {
                "chunk_id": case.id,
                "document_id": case.id,
                "document_title": "allowed",
                "chunk_index": 0,
                "content": "safe",
                "score": 1.0,
                "metadata": {},
            }
        ]

    def answer(self, request, chunks):
        raise RuntimeError("answer down")


class RetrievalServiceTarget:
    def __init__(self):
        dataset = build_acme_corp()
        document = dataset.documents["engineering/architecture-overview.md"]
        self.service = RetrievalService(
            store=SimpleNamespace(search=lambda **kwargs: []),
            load_row=lambda _document_id: SimpleNamespace(
                tenant_id=document.tenant_id,
                status=DocumentStatus.READY,
                deleted_at=None,
            ),
            policy=lambda _document_id: document.policy,
        )

    def retrieve(self, request):
        return self.service.retrieve(request)

    def answer(self, request, chunks):
        return "blocked"


def test_blocked_case_passes_when_target_returns_no_chunks() -> None:
    verdict = run_case(generate_cases()[0], EmptyTarget())

    assert verdict.passed is True
    assert verdict.observation.retrieved == ()
    assert verdict.observation.error is None


def test_blocked_case_fails_when_target_returns_content() -> None:
    verdict = run_case(generate_cases()[1], LeakyTarget())

    assert verdict.passed is False
    assert "unexpected retrieval" in verdict.reason


def test_target_errors_become_failed_observations() -> None:
    verdict = run_case(generate_cases()[0], FailingTarget())

    assert verdict.passed is False
    assert isinstance(verdict.observation, ScenarioObservation)
    assert verdict.observation.error == "target down"


def test_generation_stage_evaluates_answer_even_without_chunks() -> None:
    verdict = run_case(generate_cases()[4], GenerationLeakTarget())

    assert verdict.passed is False
    assert "answer" in verdict.reason


def test_runner_passes_typed_document_filter_to_retrieval_seam() -> None:
    target = RetrievalServiceShapeTarget()

    run_case(generate_cases()[0], target)

    assert target.request.filters["document_id"]
    assert set(target.request.filters) == {"document_id"}


def test_runner_request_is_consumable_by_retrieval_service() -> None:
    verdict = run_case(generate_cases()[0], RetrievalServiceTarget())

    assert verdict.observation.error is None


def test_runner_fails_closed_when_target_exceeds_max_top_k() -> None:
    verdict = run_case(generate_cases()[0], TooManyChunksTarget())

    assert verdict.passed is False
    assert verdict.observation.error is not None
    assert "top_k" in verdict.observation.error


def test_answer_error_preserves_retrieved_chunks() -> None:
    verdict = run_case(generate_cases()[2], AnswerFailsAfterRetrievalTarget())

    assert verdict.passed is False
    assert len(verdict.observation.retrieved) == 1
    assert verdict.observation.error == "answer down"
