# domain-models

## Requirements

### Requirement: Canonical Enums

The system MUST define `Classification` (public, internal, confidential, restricted), `DocumentStatus` (pending, ready, failed), `FindingSeverity` (low, medium, high, critical), and `ScenarioOutcome` (pass, warning, fail, critical) as `str` enums with the exact member values above; `Classification` MUST rank public < internal < confidential < restricted.

#### Scenario: Enum member values and ordering

- GIVEN the core enums
- WHEN a member value is read
- THEN `Classification.RESTRICTED.value == "restricted"`
- AND rank order comparisons behave as specified

#### Scenario: Unknown member rejected

- GIVEN a value outside an enum
- WHEN it is used as an enum member
- THEN construction fails with a validation error

### Requirement: Pydantic Models

The system MUST define Pydantic v2 models `AuthorizationContext`, `DocumentACL`, `DocumentPolicy`, `PolicyDecision`, `RetrievalRequest`, `RetrievedChunk`, `Citation`, `AttackScenario`, `EvaluationCase`, `SecurityFinding`, and `EvaluationResult` with the field names and types in TRD §3.2–§3.5 (UUIDs, sets, literals, datetimes).

#### Scenario: Validation on construction

- GIVEN valid field values for `AuthorizationContext`
- WHEN the model is instantiated
- THEN construction succeeds
- AND invalid enum or type input is rejected

### Requirement: JSONB Serialization

`AuthorizationContext` MUST serialize to and from a JSON-compatible structure (sets as arrays, UUIDs as strings) suitable for the `evaluation_cases.actor` jsonb column, and MUST round-trip losslessly.

#### Scenario: Round-trip through JSON

- GIVEN an `AuthorizationContext`
- WHEN it is dumped to JSON and re-parsed
- THEN all fields compare equal
- AND `source` preserves its literal value

### Requirement: Pure Protocols

The system MUST define protocols `RAGAdapter`, `VectorStore`, `LLMProvider`, and `EmbeddingProvider` with the method signatures in TRD §3.4, §6, §7, and §8. Model and protocol definitions MUST NOT perform any I/O.

#### Scenario: Protocol conformance

- GIVEN a stub class implementing `RAGAdapter`
- WHEN it is type-checked against the protocol
- THEN mypy accepts the implementation
- AND no model triggers network or filesystem access
