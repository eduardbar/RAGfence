"""CLI-to-canonical-evaluation integration seam tests (Work Unit F)."""

from pathlib import Path

import pytest

from ragfence.cli import seams
from ragfence.cli.config import CliConfig


def test_legacy_threshold_is_converted_to_canonical_engine_scale() -> None:
    assert seams.canonical_threshold(0.8) == 80.0
    assert seams.canonical_threshold(0.0) == 0.0
    assert seams.canonical_threshold(1.0) == 100.0

    with pytest.raises(ValueError):
        seams.canonical_threshold(1.01)


def test_reference_evaluation_constructs_db_backed_reference_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class FakeReferenceAdapter:
        def __init__(self, engine: object) -> None:
            seen["engine"] = engine

    def fake_run_matrix(target, controls, **kwargs):
        seen["target"] = target
        seen["controls"] = controls
        return ()

    def fake_evaluate_gate(results, controls, *, threshold):
        seen["threshold"] = threshold
        from ragfence.evaluation.gate import GateDecision

        return GateDecision(
            passed=True,
            reasons=(),
            security_score=1.0,
            utility_score=1.0,
            overall_score=1.0,
        )

    monkeypatch.setattr(seams, "create_engine", lambda dsn: seen.setdefault("dsn", dsn))
    monkeypatch.setattr(seams, "ReferenceAdapter", FakeReferenceAdapter)
    monkeypatch.setattr("ragfence.evaluation.matrix_runner.run_matrix", fake_run_matrix)
    monkeypatch.setattr("ragfence.evaluation.gate.evaluate_gate", fake_evaluate_gate)

    seams.evaluate(CliConfig(threshold=0.8, adapter="reference"), adapter=None, base_url=None)

    assert seen["target"].__class__ is FakeReferenceAdapter
    assert str(seen["dsn"]).startswith("postgresql+psycopg://")
    assert seen["threshold"] == 80.0


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


def test_generic_http_evaluation_uses_matrix_and_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from ragfence.adapters.generic_http import GenericHTTPAdapter, GenericHTTPConfig
    from tests.support.generic_http_stub import GenericHTTPStub, json_response

    stub = GenericHTTPStub()
    for _ in range(20):
        stub.route("POST", "/retrieve", json_response({"chunks": []}))

    adapter_config = GenericHTTPConfig.model_validate(
        {"base_url": stub.base_url, "retrieve_path": "retrieve"}
    )
    adapter = GenericHTTPAdapter(adapter_config)

    def fake_create_adapter(name: str, config: object) -> GenericHTTPAdapter:
        return adapter

    monkeypatch.setattr(seams, "create_adapter", fake_create_adapter)

    cli_config = seams.CliConfig(
        threshold=0.8,
        adapter="generic_http",
        generic_http=adapter_config,
    )
    report = seams.evaluate(cli_config, adapter=None, base_url=None)

    assert report.outcome == "fail"
    assert report.artifact["gate_passed"] is False
    assert any("identity not represented" in r for r in report.artifact["gate_reason"])
