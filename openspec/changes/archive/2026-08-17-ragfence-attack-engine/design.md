# Design: RAGFence Attack Engine

## Technical Approach

Separate declarative scenario metadata from case generation and execution. `attacks/scenarios.py` owns the catalog and stable IDs. `attacks/generators.py` creates `EvaluationCase` objects from the deterministic Acme fixture. `attacks/runner.py` owns bounded target invocation and objective verdicts. Phase 8 can consume the runner's typed observations without importing scenario implementation details.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| ADR-1 | Scenario identity | Stable slug IDs matching PRD order | Reports and persisted results need reproducible joins across runs. |
| ADR-2 | Dataset | `build_acme_corp(seed)` with fixed default seed | Existing fixture gives stable actors, documents, ACLs, and synthetic ground truth without I/O. |
| ADR-3 | Case IDs | UUID5 derived from seed + scenario ID + case ordinal | Repeated generation is byte-equivalent and idempotent. |
| ADR-4 | Execution boundary | Protocol-based `ScenarioTarget`/`RAGAdapter` seam | Attack definitions remain declarative; external systems are reached only through adapters. |
| ADR-5 | Verdict | Objective retrieval evidence plus expected behavior | Unauthorized chunks and expected blocking are mechanical; no LLM judgment is required for retrieval security. |
| ADR-6 | Safety | Synthetic-only, bounded timeout, no subprocess/network behavior in scenario definitions | This is a test harness, not a live exploit tool. |

## Scenario Catalog

| ID | Target stage | Expected behavior | Synthetic actor/input |
|----|--------------|-------------------|-----------------------|
| `cross-tenant-retrieval` | retrieval | must_block | Acme engineering actor asks for Globex content |
| `cross-department-retrieval` | retrieval | must_block | Engineering actor asks for finance payroll |
| `direct-sensitive-data` | both | must_block | Engineering actor asks for CFO salary |
| `metadata-spoofing` | retrieval | must_block | Forged tenant/department fields in request metadata |
| `prompt-injection` | generation | must_block | User asks to ignore policy and disclose restricted content |
| `indirect-prompt-injection` | generation | must_block | Poisoned retrieved content attempts instruction override |
| `document-poisoning` | both | must_block | Attacker-controlled content tries to steer answer |
| `role-escalation` | retrieval | must_block | Internal user requests restricted board plan |
| `deleted-document-retrieval` | retrieval | must_block | User requests soft-deleted document |
| `retrieval-filter-bypass` | retrieval | must_block | Negative/oversized top_k and wildcard filter attempts |

## Interfaces

```python
class ScenarioTarget(Protocol):
    def run(self, case: EvaluationCase) -> ScenarioObservation: ...

@dataclass(frozen=True)
class ScenarioObservation:
    case_id: UUID
    retrieved: tuple[RetrievedChunk, ...]
    answer: str | None
    error: str | None
    latency_ms: int

@dataclass(frozen=True)
class ScenarioVerdict:
    case: EvaluationCase
    observation: ScenarioObservation
    passed: bool
    reason: str
```

## Testing Strategy

- Catalog has exactly ten unique IDs and correct PRD ordering.
- Generation is deterministic across fresh fixture builds and seed values.
- Every case maps to a valid synthetic actor and expected behavior.
- Runner blocks unauthorized retrieved chunks and handles target errors as failed observations.
- Runner applies a bounded `top_k` policy for filter-bypass inputs.
- No network, Docker, API key, or database is needed.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/ragfence/attacks/scenarios.py` | Create | Ten declarative scenario definitions. |
| `src/ragfence/attacks/generators.py` | Create | Deterministic Acme case generation. |
| `src/ragfence/attacks/runner.py` | Create | Observation, verdict, and bounded execution seam. |
| `src/ragfence/attacks/__init__.py` | Modify | Public attack-engine exports. |
| `tests/test_attack_scenarios.py` | Create | Catalog and metadata tests. |
| `tests/test_attack_generators.py` | Create | Determinism and case integrity tests. |
| `tests/test_attack_runner.py` | Create | Objective verdict and error handling tests. |

## Phase 8 Handoff

The runner returns typed in-memory observations and verdicts only. Phase 8 owns scoring, severity mapping, persistence, and report conversion. The CLI `evaluate` seam can later call the Phase 8 engine without changing scenario definitions.
