"""Typed configuration loading for the RAGFence CLI."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic import ValidationError

from ragfence.adapters.generic_http import GenericHTTPConfig


class ConfigError(ValueError):
    """Raised when the CLI configuration is missing or invalid."""


@dataclass(frozen=True)
class CliConfig:
    """Validated settings shared by Phase 6 commands."""

    threshold: float = 0.8
    adapter: str = "reference"
    generic_http: GenericHTTPConfig | None = None


def apply_profile(settings: CliConfig, profile: str) -> CliConfig:
    """Apply a policy profile without mutating the loaded configuration.

    CLI configuration thresholds use the legacy 0–1 scale, so the profile
    boundaries of 95 and 60 are represented as 0.95 and 0.60 here.  The
    evaluation seam converts the resulting value to its 0–100 scale.
    """
    if profile == "default":
        threshold = settings.threshold
    elif profile == "strict":
        threshold = max(settings.threshold, 0.95)
    elif profile == "permissive":
        threshold = min(settings.threshold, 0.60)
    else:
        raise ValueError(f"unsupported policy profile: {profile}")
    return replace(settings, threshold=threshold)


def load_config(
    path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    base_url_override: str | None = None,
    require: bool = False,
) -> CliConfig:
    """Load TOML settings and apply ``RAGFENCE_`` environment overrides.

    With ``require=True`` (an explicitly passed ``--config``), a missing file is
    a fail-closed ``ConfigError`` instead of a silent fallback to defaults.
    """
    config_path = path or Path("ragfence.toml")
    values: dict[str, object] = {}
    if config_path.exists():
        try:
            with config_path.open("rb") as stream:
                loaded = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"invalid configuration: {config_path}") from exc
        values.update(loaded)
    elif require:
        raise ConfigError(f"configuration not found: {config_path}; run 'ragfence init' first")

    env = os.environ if environ is None else environ
    if "RAGFENCE_THRESHOLD" in env:
        values["threshold"] = env["RAGFENCE_THRESHOLD"]
    if "RAGFENCE_ADAPTER" in env:
        values["adapter"] = env["RAGFENCE_ADAPTER"]

    raw_threshold = values.get("threshold", 0.8)
    if not isinstance(raw_threshold, (str, int, float)):
        raise ConfigError("threshold must be a number between 0 and 1")
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError) as exc:
        raise ConfigError("threshold must be a number between 0 and 1") from exc
    if not 0 <= threshold <= 1:
        raise ConfigError("threshold must be a number between 0 and 1")

    adapter = values.get("adapter", "reference")
    if not isinstance(adapter, str) or not adapter:
        raise ConfigError("adapter must be a non-empty string")

    generic_raw = values.get("adapters", {})
    if generic_raw is None:
        generic_raw = {}
    if not isinstance(generic_raw, Mapping):
        raise ConfigError("adapters must be a table")
    generic_section = generic_raw.get("generic_http")
    generic_http: GenericHTTPConfig | None = None
    if generic_section is not None:
        if not isinstance(generic_section, Mapping):
            raise ConfigError("adapters.generic_http must be a table")
        generic_values = dict(generic_section)
        if base_url_override is not None:
            generic_values["base_url"] = base_url_override
        try:
            generic_http = GenericHTTPConfig.model_validate(generic_values)
        except ValidationError as exc:
            raise ConfigError("invalid adapters.generic_http configuration") from exc
    elif base_url_override is not None:
        raise ConfigError("base_url override requires adapters.generic_http configuration")

    return CliConfig(threshold=threshold, adapter=adapter, generic_http=generic_http)
