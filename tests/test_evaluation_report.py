import json

from ragfence.evaluation.contracts import MetricValue
from ragfence.evaluation.report import build_report, render_json, render_text


def _summary() -> dict[str, object]:
    return {
        "score": 82.5,
        "threshold": 80,
        "outcome": "pass",
        "metrics": {"z_metric": 0.2, "context_precision": 0.9},
    }


def _results() -> list[dict[str, object]]:
    return [
        {
            "case_id": "case-b",
            "passed": False,
            "findings": [
                {
                    "id": "finding-z",
                    "severity": "high",
                    "category": "leak",
                    "title": "Leak",
                    "evidence": {"content": "Bearer super-secret"},
                },
                {
                    "id": "finding-a",
                    "severity": "low",
                    "category": "other",
                    "title": "Other",
                    "evidence": {"authorization": "Bearer token"},
                },
            ],
            "retrieved": [{"chunk_id": "chunk-2", "content": "private text"}],
        },
        {"case_id": "case-a", "passed": True, "findings": [], "retrieved": []},
    ]


def test_report_json_is_canonical_and_orders_cases_findings() -> None:
    first = render_json(build_report(_summary(), _results()))
    second = render_json(build_report(_summary(), list(reversed(_results()))))

    assert first == second
    payload = json.loads(first)
    assert list(payload) == ["metrics", "outcome", "results", "score", "threshold"]
    assert [result["case_id"] for result in payload["results"]] == ["case-a", "case-b"]
    assert [finding["id"] for finding in payload["results"][1]["findings"]] == [
        "finding-a",
        "finding-z",
    ]
    assert payload["score"] == 82.5
    assert payload["threshold"] == 80
    assert payload["outcome"] == "pass"
    assert payload["metrics"] == {"context_precision": 0.9, "z_metric": 0.2}


def test_report_redacts_evidence_and_does_not_emit_chunk_content() -> None:
    payload = json.loads(render_json(build_report(_summary(), _results())))
    encoded = json.dumps(payload)

    assert "super-secret" not in encoded
    assert "private text" not in encoded
    assert "[REDACTED]" in encoded
    assert payload["results"][1]["retrieved"] == ["chunk-2"]


def test_timestamp_is_omitted_by_default_and_injected_when_supplied() -> None:
    without = json.loads(render_json(build_report(_summary(), [])))
    with_timestamp = json.loads(
        render_json(build_report(_summary(), [], timestamp="2026-08-17T12:00:00Z"))
    )

    assert "timestamp" not in without
    assert with_timestamp["timestamp"] == "2026-08-17T12:00:00Z"


def test_text_projection_contains_explicit_score_threshold_outcome_and_metrics() -> None:
    text = render_text(build_report(_summary(), _results()))

    assert "Score: 82.5/100" in text
    assert "Threshold: 80/100" in text
    assert "Outcome: pass" in text
    assert "context_precision=0.9" in text


def test_report_preserves_unavailable_metric_policy_without_inventing_values() -> None:
    summary = _summary()
    summary["metrics"] = {
        "faithfulness": MetricValue.unavailable("faithfulness", "generation evidence not supplied"),
        "cost_usd": MetricValue.unavailable("cost_usd", "adapter did not supply cost"),
    }

    payload = json.loads(render_json(build_report(summary, [])))

    assert payload["metrics"]["faithfulness"]["value"] is None
    assert payload["metrics"]["faithfulness"]["policy"] == "exclude"
    assert payload["metrics"]["cost_usd"]["reason"] == "adapter did not supply cost"
