"""CLI-to-canonical-evaluation integration seam tests (Work Unit F)."""

from pathlib import Path

import pytest

from ragfence.cli import seams
from ragfence.cli.config import CliConfig
from ragfence.cli.reporting import EvaluationReport


def test_legacy_threshold_is_converted_to_canonical_engine_scale() -> None:
    assert seams.canonical_threshold(0.8) == 80.0
    assert seams.canonical_threshold(0.0) == 0.0
    assert seams.canonical_threshold(1.0) == 100.0

    with pytest.raises(ValueError):
        seams.canonical_threshold(1.01)


def test_evaluate_runs_engine_and_builds_canonical_report(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeSummary:
        score = 91.5
        threshold = 80.0
        outcome = "PASS"
        results = ()

    class FakeEngine:
        def __init__(self, target: object, *, threshold: float) -> None:
            seen["target"] = target
            seen["threshold"] = threshold

        def run(self) -> FakeSummary:
            return FakeSummary()

    def fake_build_report(summary: object, results: object) -> object:
        seen["summary"] = summary
        seen["results"] = results
        return type("Artifact", (), {"payload": {"score": 91.5, "threshold": 80.0}})()

    monkeypatch.setattr(seams, "EvaluationEngine", FakeEngine)
    monkeypatch.setattr(seams, "build_report", fake_build_report)

    report = seams.evaluate(CliConfig(threshold=0.8), adapter=None, base_url=None)

    assert isinstance(report, EvaluationReport)
    assert seen["threshold"] == 80.0
    assert report.score == 91.5
    assert report.threshold == 80.0
    assert report.artifact == {"score": 91.5, "threshold": 80.0}


@pytest.mark.parametrize(
    ("adapter", "base_url"),
    [("generic_http", None), (None, "http://target.example")],
)
def test_evaluate_rejects_external_target_without_evaluating_reference(
    monkeypatch: pytest.MonkeyPatch,
    adapter: str | None,
    base_url: str | None,
) -> None:
    def fail_if_reference_target_is_constructed() -> None:
        raise AssertionError("external target must not fall back to _ReferenceTarget")

    monkeypatch.setattr(seams, "_ReferenceTarget", fail_if_reference_target_is_constructed)

    with pytest.raises(seams.RuntimeCommandError, match="external adapter target"):
        seams.evaluate(CliConfig(threshold=0.8), adapter=adapter, base_url=base_url)


def test_evaluate_rejects_non_reference_configured_adapter() -> None:
    with pytest.raises(seams.RuntimeCommandError, match="external adapter target"):
        seams.evaluate(
            CliConfig(threshold=0.8, adapter="generic_http"),
            adapter=None,
            base_url=None,
        )


def test_evaluate_rejects_base_url_even_for_reference_adapter() -> None:
    with pytest.raises(seams.RuntimeCommandError, match="external adapter target"):
        seams.evaluate(
            CliConfig(threshold=0.8), adapter="reference", base_url="http://target.example"
        )


def test_evaluate_rejects_invalid_legacy_threshold() -> None:
    with pytest.raises(ValueError):
        seams.evaluate(CliConfig(threshold=1.1), adapter=None, base_url=None)


def test_default_report_path_stays_json_under_project_reports(tmp_path: Path) -> None:
    assert seams.default_report_path(tmp_path / "ragfence.toml", json_output=True) == (
        tmp_path / ".ragfence" / "reports" / "latest.json"
    )
