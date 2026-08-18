"""Declarative attack scenario catalog and runner seams."""

from ragfence.attacks.generators import MAX_TOP_K, bounded_top_k, generate_cases, validate_filters
from ragfence.attacks.runner import ScenarioObservation, ScenarioOracle, ScenarioVerdict, run_case
from ragfence.attacks.scenarios import scenario_catalog

__all__ = [
    "ScenarioObservation",
    "ScenarioOracle",
    "ScenarioVerdict",
    "MAX_TOP_K",
    "bounded_top_k",
    "generate_cases",
    "run_case",
    "scenario_catalog",
    "validate_filters",
]
