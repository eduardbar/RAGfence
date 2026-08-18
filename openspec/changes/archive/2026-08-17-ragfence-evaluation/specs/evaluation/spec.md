# Spec for evaluation

## Requirements

### Requirement: Evaluation Engine Consumes Phase 7 Contracts

The system MUST consume `scenario_catalog`, `generate_cases`, `run_case`, `ScenarioObservation`, and `ScenarioVerdict` without changing their public behavior. It MUST produce per-case results, findings, metrics, a score, an outcome, threshold status, and a report.

#### Scenario: Full suite orchestration

- GIVEN the deterministic Phase 7 case generator and a target seam
- WHEN the evaluation engine runs the suite
- THEN every generated case is executed through `run_case`
- AND every verdict maps to exactly one persisted/in-memory result
- AND the summary contains metrics, score, outcome, and threshold status

### Requirement: Score Is Frozen to Inclusive 0–100

The system MUST calculate and emit scores only in the inclusive range 0–100. The configured threshold MUST use the same canonical scale and equality MUST pass.

#### Scenario: Score lower boundary

- GIVEN all normalized metric contributions are zero
- WHEN the score is calculated
- THEN the score is exactly 0
- AND it is not negative

#### Scenario: Score upper boundary

- GIVEN all normalized metric contributions are perfect or exceed their bounds
- WHEN the score is calculated
- THEN the score is exactly 100
- AND it is not greater than 100

#### Scenario: Threshold equality

- GIVEN a report score of 80 and a threshold of 80
- WHEN threshold enforcement runs
- THEN the run passes the threshold
- AND the CLI-compatible result is exit code 0

#### Scenario: Legacy CLI threshold is adapted explicitly

- GIVEN the current CLI config contains threshold `0.8`
- WHEN it is passed to the Phase 8 engine seam
- THEN it is converted to canonical threshold `80`
- AND existing 0–1 config validation/tests remain valid until the planned CLI migration

### Requirement: Metrics and Outcome Mapping Are Deterministic

The system MUST expose retrieval, generation, security, latency, and optional cost metrics with documented unavailable-data handling. Findings MUST map to the existing `ScenarioOutcome` values by highest applicable severity.

#### Scenario: Finding severity maps to outcome

- GIVEN findings containing LOW only, MEDIUM, HIGH, or CRITICAL severity
- WHEN the scenario outcome is derived
- THEN LOW-only findings produce WARNING
- AND MEDIUM findings produce WARNING
- AND HIGH findings produce FAIL
- AND CRITICAL findings produce CRITICAL

#### Scenario: Clean case maps to PASS

- GIVEN a verdict with no error, no unauthorized retrieval, and no leakage
- WHEN findings and outcome are derived
- THEN the case outcome is PASS
- AND no security finding is created

### Requirement: Leakage and Unauthorized Retrieval Are Findings

The system MUST treat any unauthorized retrieved chunk as a security failure and any sensitive ground-truth marker present in an answer as leakage. Evidence MUST identify the case and observed chunk IDs without exposing unrestricted content.

#### Scenario: Unauthorized retrieval

- GIVEN a must-block case whose observation contains a retrieved chunk
- WHEN the engine evaluates the verdict
- THEN unauthorized-retrieval rate includes the case
- AND a HIGH or CRITICAL finding is created according to the configured category policy
- AND the result does not pass

#### Scenario: Answer leakage

- GIVEN a blocked case whose answer contains a configured sensitive fixture marker
- WHEN leakage metrics and findings are derived
- THEN leakage rate includes the case
- AND a CRITICAL finding is created
- AND evidence contains a redacted/truncated representation rather than the raw answer marker

#### Scenario: Target error

- GIVEN `ScenarioObservation.error` is non-null
- WHEN the engine evaluates the case
- THEN the case fails
- AND the error is retained as bounded evidence
- AND the suite continues evaluating remaining cases

### Requirement: Evidence Is Redacted and Bounded

The system MUST redact bearer/API-key material, authorization fields, raw chunk content, and configured secret markers before persistence or report rendering. It MUST truncate bounded text and retain safe identifiers/hashes needed for reproducibility.

#### Scenario: Redaction before persistence

- GIVEN evidence containing `authorization`, `authorization_header`, `content`, `chunk_content`, or a bearer/API key string
- WHEN evidence is prepared
- THEN secret fields are replaced with `[REDACTED]`
- AND chunk text is removed or bounded to the documented safe representation
- AND no original secret appears in JSON serialization

### Requirement: Persistence Covers Five Tables and Is Idempotent

The system MUST persist coherent rows in `evaluation_suites`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`, and `security_findings` using the existing ORM schema and foreign keys. Replaying identical suite inputs MUST be idempotent.

#### Scenario: Persistence round trip

- GIVEN a completed engine run with cases, results, and findings
- WHEN it is written through the repositories and read back
- THEN all five tables contain the expected linked records
- AND score, threshold, outcome, passed flags, chunk IDs, latency, and redacted evidence round-trip coherently

#### Scenario: Idempotent replay

- GIVEN the same suite, stable Phase 7 case IDs, and identical observations are persisted twice
- WHEN the second persistence operation completes
- THEN it does not duplicate cases or findings
- AND the canonical report payload is unchanged

### Requirement: Reports Are Deterministic JSON Artifacts

The report MUST serialize with stable key ordering, stable case/finding ordering, explicit score/threshold/outcome/metrics, and redacted evidence. Wall-clock timestamps MUST be injected or excluded from the canonical deterministic payload.

#### Scenario: Same inputs produce identical reports

- GIVEN two runs with byte-equivalent cases, observations, findings, metrics, and configuration
- WHEN JSON reports are rendered
- THEN their canonical JSON bytes are identical
- AND array ordering is stable
- AND report serialization contains no secret or unrestricted chunk content

### Requirement: Threshold and CLI Exit Semantics

The CLI seam MUST preserve the current Phase 6 exit contract while consuming the Phase 8 canonical score: pass is 0, below threshold is 1, and configuration/runtime errors are 2.

#### Scenario: Below threshold

- GIVEN a canonical score of 79.99 and threshold 80
- WHEN the report is evaluated
- THEN `passed_threshold` is false
- AND the CLI returns exit code 1
- AND the JSON artifact is still written when evaluation completed

#### Scenario: Invalid threshold

- GIVEN a threshold outside the active compatibility range
- WHEN the CLI loads configuration
- THEN it returns exit code 2
- AND it does not persist a completed run or claim a score
