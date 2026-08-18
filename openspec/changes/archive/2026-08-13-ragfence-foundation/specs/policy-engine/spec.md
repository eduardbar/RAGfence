# Delta for policy-engine

## ADDED Requirements

### Requirement: Decision Function

The system MUST expose a pure, deterministic function that accepts a `DocumentPolicy` and an `AuthorizationContext` and returns a `PolicyDecision` with `allowed`, `reasons`, and `evaluated_at`. The function MUST perform no I/O. Row-state rules (deleted_at, status, tenant) are enforced by the storage layer before this pure decision runs.

#### Scenario: Cross-department denial (success criterion)

- GIVEN a finance, confidential document policy and an `engineering_employee` context (engineering, internal)
- WHEN the decision is evaluated
- THEN `allowed` is false
- AND `reasons` is non-empty and names the failing rules

### Requirement: Deny-by-Default

The decision MUST deny any access not explicitly granted by the TRD §5.3 rules: classification rank (rule 4), explicit user allowlist (rule 5), explicit group allowlist (rule 6), and department scoping (rules 7–8); everything else MUST be denied (rule 9).

#### Scenario: No implicit access

- GIVEN a policy with `department_id` null and empty allowlists
- WHEN the decision is evaluated
- THEN `allowed` is false

### Requirement: Classification Escalation

The decision MUST deny when the policy's `classification` rank exceeds the context's `classification` rank.

#### Scenario: Clearance below document

- GIVEN an `INTERNAL` context and a `RESTRICTED` policy
- WHEN the decision is evaluated
- THEN `allowed` is false
- AND a reason names the classification rule

### Requirement: Explicit Grants Override Department

The decision MUST allow when `ctx.user_id` is in `allowed_user_ids` or `ctx.allowed_group_ids` intersects `allowed_group_ids`, regardless of department mismatch.

#### Scenario: Allowlisted user crosses departments

- GIVEN a finance policy whose `allowed_user_ids` contains the user, and an engineering context
- WHEN the decision is evaluated
- THEN `allowed` is true

### Requirement: Department Scoping

The decision MUST allow a policy whose `department_id` equals `ctx.department_id`, and MUST deny when `department_id` is null without an explicit grant.

#### Scenario: Same-department allow

- GIVEN a policy with `department_id == ctx.department_id` and no explicit grants
- WHEN the decision is evaluated
- THEN `allowed` is true

### Requirement: Authorization Before Retrieval

The retrieval flow MUST evaluate the policy decision before performing any retrieval; a DENY MUST prevent retrieval entirely.

#### Scenario: Denied request never retrieves

- GIVEN a denied `PolicyDecision`
- WHEN a retrieval is attempted
- THEN no retrieval call is executed
