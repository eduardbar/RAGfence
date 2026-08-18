"""Configuration contract tests for the Phase 6 CLI."""

from pathlib import Path

import pytest

from ragfence.cli.config import CliConfig, ConfigError, load_config


def test_load_config_reads_toml_values(tmp_path: Path) -> None:
    config_path = tmp_path / "ragfence.toml"
    config_path.write_text("threshold = 0.8\nadapter = 'reference'\n", encoding="utf-8")

    config = load_config(config_path, environ={})

    assert config == CliConfig(threshold=0.8, adapter="reference")


def test_environment_overrides_file_values(tmp_path: Path) -> None:
    config_path = tmp_path / "ragfence.toml"
    config_path.write_text("threshold = 0.8\n", encoding="utf-8")

    config = load_config(config_path, environ={"RAGFENCE_THRESHOLD": "0.9"})

    assert config.threshold == 0.9


def test_invalid_threshold_raises_config_error(tmp_path: Path) -> None:
    config_path = tmp_path / "ragfence.toml"
    config_path.write_text("threshold = 1.5\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="threshold"):
        load_config(config_path, environ={})


def test_malformed_toml_raises_config_error(tmp_path: Path) -> None:
    config_path = tmp_path / "ragfence.toml"
    config_path.write_text("threshold = [", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid configuration"):
        load_config(config_path, environ={})
