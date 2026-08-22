"""Declarative attack scenario catalog and runner seams."""

from ragfence.attacks.generators import (
    MAX_TOP_K,
    bounded_top_k,
    generate_cases,
    generate_indirect_injection_cases,
    generate_indirect_prompt_injection_cases,
    generate_injection_cases,
    validate_filters,
)
from ragfence.attacks.runner import ScenarioObservation, ScenarioOracle, ScenarioVerdict, run_case
from ragfence.attacks.scenarios import (
    indirect_prompt_injection_catalog,
    indirect_prompt_injection_scenarios,
    injection_scenario_catalog,
    scenario_catalog,
)

__all__ = [
    "ScenarioObservation",
    "ScenarioOracle",
    "ScenarioVerdict",
    "MAX_TOP_K",
    "bounded_top_k",
    "generate_cases",
    "generate_injection_cases",
    "generate_indirect_injection_cases",
    "generate_indirect_prompt_injection_cases",
    "run_case",
    "scenario_catalog",
    "injection_scenario_catalog",
    "indirect_prompt_injection_catalog",
    "indirect_prompt_injection_scenarios",
    "validate_filters",
]
