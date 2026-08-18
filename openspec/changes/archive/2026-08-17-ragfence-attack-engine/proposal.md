# Proposal: RAGFence Attack Engine (Phase 7)

## Intent

Implement the deterministic adversarial scenario library for RAGFence (IMPLEMENTATION_PLAN Phase 7). The engine will define the ten v0.1 attack classes from `docs/PRD.md`, generate reproducible `EvaluationCase` inputs against the synthetic Acme dataset, and provide an execution seam for Phase 8 evaluation orchestration.

## Scope

### In Scope

- Declarative definitions for all ten v0.1 `AttackScenario` classes.
- Deterministic case generation from the fixed Acme dataset and seed.
- Scenario metadata: retrieval/generation target stage and expected allow/block behavior.
- A narrow scenario execution protocol that consumes a target `RAGAdapter` and returns case observations.
- Objective verdict logic for expected allow/block versus observed retrieval behavior.
- Synthetic-only fixtures and tests; bounded execution and no live-target discovery.

### Out of Scope

- Weighted scoring, persistence, report orchestration, and threshold handling (Phase 8).
- Generic HTTP adapter implementation (Phase 9).
- Real LLM providers (Phase 10).
- CLI command wiring beyond the existing Phase 6 seam.

## Ten v0.1 Scenarios

1. Cross-tenant retrieval
2. Cross-department retrieval
3. Direct sensitive-data request
4. Metadata spoofing
5. Prompt injection
6. Indirect prompt injection
7. Document poisoning
8. Role escalation
9. Deleted-document retrieval
10. Retrieval filter bypass

## Dependencies

- Completed Phases 0–6: core models/protocols, deterministic Acme fixture, secure retrieval, and CLI seams.
- `AttackScenario`, `EvaluationCase`, `RetrievedChunk`, and `RAGAdapter` contracts.

## Success Criteria

- Exactly ten unique scenario definitions exist and match the PRD IDs.
- Repeated generation with the same seed produces byte-equivalent case payloads.
- Every generated case has a valid actor, prompt, scenario ID, and objective expected behavior.
- Execution is bounded and reports a typed observation/verdict without embedding Phase 8 persistence logic.
- Focused and full quality gates remain green without PostgreSQL or API keys.
