"""docker-compose.yml validation (task 1.4).

Spec reference: openspec/changes/ragfence-foundation/specs/project-bootstrap/spec.md
- Local Services / Scenario: Compose config valid — parses, declares pgvector/pgvector:pg16.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


def test_compose_declares_pinned_pgvector_image() -> None:
    content = COMPOSE.read_text(encoding="utf-8")
    assert "pgvector/pgvector:pg16" in content


def test_compose_declares_healthcheck() -> None:
    content = COMPOSE.read_text(encoding="utf-8")
    assert "healthcheck" in content
    assert "pg_isready" in content


def test_compose_maps_host_port() -> None:
    content = COMPOSE.read_text(encoding="utf-8")
    assert "${RAGFENCE_DB_PORT:-5434}:5432" in content


@pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker unavailable; static checks above still validate the file",
)
def test_docker_compose_config_parses() -> None:
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
