# Spec for attack-engine

## Requirements

### Requirement: Complete Scenario Catalog

The system MUST expose exactly ten unique v0.1 attack scenarios matching the canonical IDs and order in `docs/PRD.md`. Each scenario MUST declare a target stage and expected behavior.

#### Scenario: Catalog contains all v0.1 attacks

- GIVEN the attack scenario catalog
- WHEN it is loaded
- THEN it contains exactly ten unique IDs
- AND the IDs match the ten PRD attack classes
- AND each item has `target_stage` and `expected_behavior`

### Requirement: Deterministic Case Generation

The system MUST generate `EvaluationCase` objects from the deterministic Acme fixture. The same seed MUST produce byte-equivalent serialized cases, stable case IDs, and valid synthetic authorization actors.

#### Scenario: Same seed produces same cases

- GIVEN two fresh Acme fixture builds with the same seed
- WHEN attack cases are generated
- THEN their canonical serialized representations are identical
- AND their case IDs are identical

#### Scenario: Every case has valid security context

- GIVEN the generated v0.1 cases
- WHEN each case is inspected
- THEN its scenario ID exists in the catalog
- AND its actor is authenticated with `source="synthetic"`
- AND `expected_allow` matches the scenario expected behavior

### Requirement: Bounded Scenario Execution

The runner MUST execute a case through an injected target seam without scenario definitions performing network, subprocess, or database operations. Target errors MUST become typed observations and MUST NOT crash the suite.

#### Scenario: Target observation becomes a verdict

- GIVEN a target that returns retrieved chunks and an answer
- WHEN a case is executed
- THEN the runner returns an observation containing the case ID, retrieved chunks, answer, and latency
- AND it returns a boolean verdict with a reason

#### Scenario: Target error is contained

- GIVEN a target that raises a runtime error
- WHEN a case is executed
- THEN the runner returns a failed observation with an error description
- AND the runner does not raise the target exception

### Requirement: Security Verdicts

The runner MUST objectively compare expected behavior with observed retrieval evidence. A must-block case MUST fail when unauthorized content is retrieved or an error indicates the target could not enforce the case. A must-block case MUST pass when no unauthorized content is retrieved and the target responds normally.

#### Scenario: Blocked case passes with no retrieval

- GIVEN a must-block case and a target returning no chunks
- WHEN the case is executed
- THEN the verdict passes

#### Scenario: Blocked case fails on retrieved content

- GIVEN a must-block case and a target returning a retrieved chunk
- WHEN the case is executed
- THEN the verdict fails
- AND the reason identifies unexpected retrieval

### Requirement: Filter Bypass Inputs Are Bounded

The retrieval filter-bypass scenario MUST use bounded, explicit adversarial inputs. The runner or generator MUST clamp unsafe `top_k` values and MUST NOT permit unbounded ranges or arbitrary executable filters.

#### Scenario: Unsafe top_k is clamped

- GIVEN the retrieval filter-bypass case
- WHEN its request is generated or normalized
- THEN `top_k` is within the configured safe maximum
- AND no executable or arbitrary SQL filter is present
