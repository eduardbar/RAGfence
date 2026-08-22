"""Release Work Unit 3: wheel-only packaging proof."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def test_wheel_installs_and_runs_outside_checkout(tmp_path: Path) -> None:
    _ = tmp_path  # noqa
    """Build a wheel, install it non-editably, and exercise import plus help."""
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    built = _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--wheel-dir",
            str(wheelhouse),
        ],
        cwd=ROOT,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheels = sorted(wheelhouse.glob("ragfence-*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
    assert "ragfence/cli/main.py" in names
    assert "ragfence/db/models.py" in names
    assert any(name.endswith("entry_points.txt") for name in names)
    assert not any(name.startswith(("tests/", "docs/", ".github/")) for name in names)
    assert not any(name.lower().endswith((".env", ".env.example")) for name in names)
    assert not any(
        name.startswith(("ragfence-", "tests/", "docs/")) for name in names if "/" not in name
    )

    venv_dir = tmp_path / "fresh-venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(venv_dir)
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    installed = _run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])], cwd=tmp_path
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    # The repository's uv environment supplies already-cached runtime wheels;
    # only dependency imports are exposed, never the checkout itself.
    env["PYTHONPATH"] = os.pathsep.join(
        str(path) for path in (ROOT / ".venv" / "Lib" / "site-packages",) if path.is_dir()
    )
    probe = _run(
        [str(python), "-c", "import ragfence; print(ragfence.__version__)"],
        cwd=tmp_path,
        env=env,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    import ragfence

    assert probe.stdout.strip() == ragfence.__version__
    script = venv_dir / ("Scripts/ragfence.exe" if os.name == "nt" else "bin/ragfence")
    help_result = _run([str(script), "--help"], cwd=tmp_path, env=env)
    assert help_result.returncode == 0, help_result.stdout + help_result.stderr
    assert "Usage" in help_result.stdout


def test_wheel_ships_reference_environment(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """El wheel incluye docker-compose.yml + migraciones Alembic del entorno de referencia."""
    wheelhouse = tmp_path_factory.mktemp("refwheel")
    built = _run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", str(wheelhouse)],
        cwd=ROOT,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheels = sorted(wheelhouse.glob("ragfence-*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        assert "ragfence/reference/docker-compose.yml" in names
        assert "ragfence/reference/alembic.ini" in names
        assert "ragfence/reference/alembic/env.py" in names
        assert any(
            name.startswith("ragfence/reference/alembic/versions/") and name.endswith(".py")
            for name in names
        ), "migraciones Alembic ausentes del wheel"


def test_packaged_reference_environment_matches_checkout() -> None:
    """Las copias empaquetadas están sincronizadas con los originales del checkout."""
    packaged = ROOT / "src" / "ragfence" / "reference"
    originals = {
        "docker-compose.yml": ROOT / "docker-compose.yml",
        "alembic.ini": ROOT / "alembic.ini",
        "alembic/env.py": ROOT / "alembic" / "env.py",
        "alembic/script.py.mako": ROOT / "alembic" / "script.py.mako",
    }
    versions = sorted((ROOT / "alembic" / "versions").glob("*.py"))
    assert versions, "el checkout debe tener migraciones"
    for relative in versions:
        originals[f"alembic/versions/{relative.name}"] = relative

    missing = [relative for relative in originals if not (packaged / relative).is_file()]
    assert not missing, f"archivos de referencia no empaquetados: {missing}"

    drifted = [
        relative
        for relative, source in originals.items()
        if (packaged / relative).read_text(encoding="utf-8") != source.read_text(encoding="utf-8")
    ]
    assert not drifted, f"copias desincronizadas con el checkout: {drifted}"
