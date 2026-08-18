"""Release Work Unit 3: wheel-only packaging proof."""

from __future__ import annotations

import os
import subprocess
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def test_wheel_installs_and_runs_outside_checkout(tmp_path: Path) -> None:
    """Build a wheel, install it non-editably, and exercise import plus help."""
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    built = _run(["uv", "build", "--wheel", "--out-dir", str(wheelhouse)], cwd=ROOT)
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
    assert probe.stdout.strip() == "0.1.0"
    help_result = _run([str(venv_dir / "Scripts/ragfence.exe"), "--help"], cwd=tmp_path, env=env)
    assert help_result.returncode == 0, help_result.stdout + help_result.stderr
    assert "Usage" in help_result.stdout
