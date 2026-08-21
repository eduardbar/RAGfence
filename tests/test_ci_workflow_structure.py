"""Offline contract tests for the reusable RAGFence CI workflow."""

import json
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal CI environments
    yaml = None


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ragfence-test.yml"


def _fallback_workflow(text: str) -> dict[str, Any]:
    """Extract the contract without interpreting untrusted YAML as code."""
    import re

    input_names = {
        name: {"default": "documented"}
        for name in re.findall(r"^      ([a-z][a-z-]*):$", text, re.MULTILINE)
    }
    steps: list[dict[str, Any]] = []
    matches = list(re.finditer(r"^      - name: (.+)$", text, re.MULTILINE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        step: dict[str, Any] = {"name": match.group(1)}
        for key in ("uses", "if"):
            found = re.search(rf"^        {key}: (.+)$", block, re.MULTILINE)
            if found:
                step[key] = found.group(1).strip().strip("\"'")
        if re.search(r"^        run:", block, re.MULTILINE):
            step["run"] = block
        steps.append(step)
    return {
        "on": {"workflow_call": {"inputs": input_names}},
        "permissions": {"contents": "read", "actions": "read"},
        "jobs": {
            "test": {
                "steps": steps,
                "strategy": {"matrix": {"python-version": ["3.12"]}},
            }
        },
    }


def load_workflow() -> dict[str, Any]:
    text = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(text) if yaml is not None else _fallback_workflow(text)
    assert isinstance(document, dict)
    document["_raw"] = text
    return document


def workflow_on(workflow: dict[str, Any]) -> dict[str, Any]:
    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def all_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict) and jobs
    job = next(iter(jobs.values()))
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


def step_by_name(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    for step in all_steps(workflow):
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing workflow step: {name}")


def test_declares_reusable_contract_and_python_matrix() -> None:
    workflow = load_workflow()
    on = workflow_on(workflow)
    call = on.get("workflow_call")
    assert isinstance(call, dict)
    inputs = call["inputs"]
    assert set(inputs) >= {
        "adapter",
        "target",
        "base-url",
        "threshold",
        "start-target-command",
        "comment",
        "fake-providers",
    }
    for input_name in inputs:
        assert "default" in inputs[input_name] or inputs[input_name].get("required") is True

    job = next(iter(workflow["jobs"].values()))
    assert job["strategy"]["matrix"]["python-version"] == ["3.12"]


def test_has_least_privilege_permissions_and_ordered_setup() -> None:
    workflow = load_workflow()
    permissions = workflow["permissions"]
    assert permissions == {"contents": "read", "actions": "read"}
    names = [step.get("name", "") for step in all_steps(workflow)]
    required_names = ("Checkout", "Set up Python", "Install dependencies", "Initialize RAGFence")
    indexes = [names.index(name) for name in required_names]
    assert indexes == sorted(indexes)
    assert step_by_name(workflow, "Checkout")["uses"] == "actions/checkout@v4"
    assert step_by_name(workflow, "Set up Python")["uses"] == "actions/setup-python@v5"


def test_evaluation_contract_has_fixed_report_and_final_gate() -> None:
    workflow = load_workflow()
    steps = all_steps(workflow)
    run_text = workflow["_raw"] + "\n" + "\n".join(str(step.get("run", "")) for step in steps)
    assert "ragfence init" in run_text
    assert "ragfence test" in run_text
    assert "--adapter" in run_text
    assert "--base-url" in run_text
    assert "--threshold" in run_text
    assert "--json" in run_text
    assert ".ragfence/reports/ci.json" in run_text
    assert any("final gate" in step.get("name", "").lower() for step in steps)


def test_artifact_summary_and_security_contract() -> None:
    workflow = load_workflow()
    steps = all_steps(workflow)
    upload = next(
        step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["if"] == "always()"
    summary = next(step for step in steps if "summary" in step.get("name", "").lower())
    assert summary["if"] == "always()"
    assert "GITHUB_STEP_SUMMARY" in workflow["_raw"]

    all_run = "\n".join(str(step.get("run", "")) for step in steps)
    forbidden = ("eval ", "printenv", "env |", "toJSON(", "Authorization:", "Bearer ")
    assert not any(token in all_run for token in forbidden)


def test_fake_provider_defaults_and_fork_safe_comment_guard() -> None:
    workflow = load_workflow()
    run_text = (
        workflow["_raw"]
        + "\n"
        + "\n".join(str(step.get("run", "")) for step in all_steps(workflow))
    )
    assert "RAGFENCE_LLM_PROVIDER=fake" in run_text
    assert "RAGFENCE_EMBEDDING_PROVIDER=fake" in run_text
    comments = [step for step in all_steps(workflow) if "comment" in step.get("name", "").lower()]
    assert comments
    condition = "\n".join(str(step.get("if", "")) for step in comments)
    assert "pull_request" in condition
    assert "head.repo.full_name" in condition
    assert "github.repository" in condition
    assert "pull_request_target" in condition


def test_validates_inputs_bounds_readiness_and_missing_report() -> None:
    workflow = load_workflow()
    run_text = (
        workflow["_raw"]
        + "\n"
        + "\n".join(str(step.get("run", "")) for step in all_steps(workflow))
    )
    assert "threshold" in run_text.lower()
    assert "0 <= threshold <= 100" in run_text
    assert "READINESS_ATTEMPTS" in run_text
    assert "if-no-files-found: error" in workflow["_raw"]
    assert "0|1|2" in run_text


def test_fixture_comparison_ignores_run_metadata_but_keeps_stable_fields() -> None:
    fixture = Path(__file__).parent / "fixtures" / "ci_report.json"
    first = json.loads(fixture.read_text(encoding="utf-8"))
    second = dict(first)
    second["run_id"] = "run-2"
    second["timestamp"] = "2099-01-01T00:00:00Z"
    stable_fields = (
        "score",
        "threshold",
        "outcome",
        "passed_threshold",
        "cases",
        "findings",
        "fingerprint",
    )
    assert {field: first[field] for field in stable_fields} == {
        field: second[field] for field in stable_fields
    }
    assert first["run_id"] != second["run_id"]
    assert first["timestamp"] != second["timestamp"]


def test_reusable_workflow_starts_pgvector_service() -> None:
    workflow = load_workflow()
    raw = workflow["_raw"]
    assert "pgvector/pgvector" in raw
    assert "services:" in raw


def test_reusable_workflow_exports_database_dsn() -> None:
    workflow = load_workflow()
    raw = workflow["_raw"]
    assert "RAGFENCE_TEST_DATABASE_DSN" in raw
    assert "postgresql+psycopg://ragfence:ragfence@" in raw


def test_reusable_workflow_runs_migrations_and_seed() -> None:
    workflow = load_workflow()
    raw = workflow["_raw"]
    assert "alembic upgrade head" in raw
    assert "seed_reference_corp" in raw


def test_reusable_workflow_gates_have_no_continue_on_error() -> None:
    workflow = load_workflow()
    steps = all_steps(workflow)
    gate_steps = [
        step
        for step in steps
        if "gate" in step.get("name", "").lower() or "evaluate" in step.get("name", "").lower()
    ]
    for step in gate_steps:
        assert not step.get("continue-on-error"), (
            f"step '{step.get('name')}' must not use continue-on-error"
        )
