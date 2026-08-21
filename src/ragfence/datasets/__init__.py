"""Deterministic Acme Corp synthetic dataset (PR 1: org model, corpus, checksums; PR 2: loader)."""

from ragfence.datasets.acme import (
    AcmeCorpDataset,
    AcmeDepartment,
    AcmeDocument,
    AcmeGroup,
    AcmeTenant,
    AcmeUser,
    build_acme_corp,
    build_globex_corp,
)
from ragfence.datasets.constants import SEED
from ragfence.datasets.loader import seed_acme_corp, seed_reference_corp

__all__ = [
    "AcmeCorpDataset",
    "AcmeDepartment",
    "AcmeDocument",
    "AcmeGroup",
    "AcmeTenant",
    "AcmeUser",
    "SEED",
    "build_acme_corp",
    "build_globex_corp",
    "seed_acme_corp",
    "seed_reference_corp",
]
