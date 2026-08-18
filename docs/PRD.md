# RAGFence — Product Requirements Document

**Tagline:** Security testing and authorization-aware retrieval for production RAG systems.

**Document status:** v0.1 draft
**Audience:** engineering, product, and security stakeholders
**Scope:** product definition, requirements, and success criteria for the RAGFence v0.1 release.

---

## 1. Overview

RAGFence is a security testing and authorization-aware retrieval framework for Retrieval-Augmented Generation (RAG) systems. It is NOT another "chat with your PDF" application. RAGFence answers one specific question that production RAG systems routinely get wrong:

> Can a RAG system retrieve or reveal documents that the authenticated user should not be able to query?

RAGFence combines secure retrieval, authorization-aware RAG, ACL enforcement, tenant isolation, RAG evaluation, security testing, adversarial test cases, and CI integration into a single open-source toolkit. It ships with a secure reference implementation AND adapters for external RAG systems.

### 1.1 Principles

1. **Open source.** Apache-2.0 license, public repository, community contributions.
2. **Local-first.** Everything runs on the developer's machine; no mandatory cloud dependency.
3. **Self-hostable.** Deploy the reference implementation and evaluation engine on your own infrastructure.
4. **BYOK (Bring Your Own Keys).** No mandatory LLM provider; users supply their own API keys or run local models.
5. **Infrastructure cost near $0.** PostgreSQL + pgvector on a laptop or a single VM is a fully functional deployment.
6. **Security enforcement OUTSIDE the LLM.** Access decisions are made by a policy engine, never by the model.
7. **Authorization BEFORE retrieval.** The authorization context is resolved and filters are applied before any vector search or LLM call happens.
8. **Never trust metadata sent by the frontend.** Authorization is derived exclusively from the authenticated backend identity.
9. **Framework agnostic when possible.** The evaluation engine speaks to RAG systems through adapters, not framework-specific APIs.
10. **Useful as both library and CLI.** `ragfence` is a CLI; its core is importable as a Python library for embedding in other tooling.

---

## 2. Problem

### 2.1 Illustrative failure

Consider the following interaction with a typical (vulnerable) RAG system:

| Actor | Question | Vulnerable RAG behavior | RAGFence expected result |
|---|---|---|---|
| `engineering_employee` (tenant `acme_corp`, department `engineering`, clearance `internal`) | "What is the CFO salary?" | Retrieves `finance/payroll/CFO.pdf` (classification `confidential`, department `finance`) and passes it into the LLM context | **BLOCKED BEFORE LLM CONTEXT.** The document never reaches the retrieval result set because the policy engine denies it at query time. |

In the vulnerable system, the user receives an answer built from a document they have no right to read. The exposure is not hypothetical: the CFO's salary lands inside the model context, and the model may reproduce it verbatim.

### 2.2 Class of failures

The core failure class is **leaking documents into the LLM context before any guardrail can act**. Once a document is inside the prompt context, the damage is done:

- The LLM cannot be the security boundary. Prompt instructions like "only use allowed documents" are not an enforcement mechanism; they are a style preference.
- Post-generation filtering (scanning the output for leaked content) is lossy and unreliable; it can never recover data already consumed by the model.
- Metadata supplied by the client (user ID, role, tenant headers) is forgeable. Systems that trust frontend metadata enable horizontal privilege escalation.

The only reliable defense is to prevent unauthorized documents from ever entering the context window. That requires enforcement at the retrieval boundary, driven by an authorization context that is derived server-side from the authenticated identity.

---

## 3. Target Users

### 3.1 AI Engineer

Builds and maintains RAG pipelines. Gets a reference implementation that demonstrates correct authorization-aware retrieval end-to-end, plus an evaluation harness to prove their pipeline does not leak. Values the ability to run `ragfence test` locally against their own adapter before shipping.

### 3.2 Backend Engineer

Owns the services that expose retrieval endpoints. Gets a clear contract for `RetrievalRequest` and `AuthorizationContext`, a FastAPI reference implementation, and a PostgreSQL/pgvector schema they can adopt. Cares about the deny-by-default policy model and the fact that enforcement lives in their layer, not in the model.

### 3.3 Security Engineer

Assesses RAG deployments for exposure. Gets a reproducible adversarial test suite (cross-tenant isolation, prompt injection, metadata spoofing, and seven more scenario classes) plus structured `SecurityFinding` output that plugs into their existing vulnerability pipeline. Values deterministic, rerunnable evidence.

### 3.4 Platform Engineer

Operates shared RAG infrastructure for many teams. Gets tenant isolation, multi-tenant schema guidance, CI integration, and a self-hostable stack with near-zero marginal infrastructure cost. Values `ragfence test --threshold` gating in pull requests.

### 3.5 Enterprise AI Team

Deploys RAG against sensitive internal data. Gets the authorization model they need (tenant, department, classification, ACL) without building it from scratch, and an evaluation suite they can extend with their own scenarios. Values local-first operation and BYOK to keep data on-premises.

### 3.6 Open Source RAG Maintainers

Maintain frameworks or libraries that other people build RAG systems with. Gets a portable adapter contract (`RAGAdapter`) and a benchmark corpus (Acme Corp) they can integrate into their own test suites to prove their framework's retrieval honors authorization. Values framework-agnostic design and a reference dataset with known ground truth.

---

## 4. Core Product Areas

### A. Secure RAG reference implementation

A full, runnable RAG pipeline that enforces authorization correctly:

```
User → Authentication → Authorization Context → ACL Policy Engine → Filtered Vector Retrieval → Reranking → LLM → Citations
```

Key behaviors:

- **Authentication** resolves the identity of the caller (reference MVP uses synthetic users; the contract is identity-agnostic).
- **Authorization Context** is built from the authenticated backend identity: `tenant_id`, `department_id`, `classification`, `allowed_users`, `allowed_groups`. It is never built from user-supplied arbitrary parameters.
- **ACL Policy Engine** evaluates each candidate document's `DocumentACL` against the `AuthorizationContext` and applies a **deny-by-default** decision.
- **Filtered Vector Retrieval** executes vector search only over documents the policy engine allowed, so unauthorized documents never enter the result set.
- **Reranking** operates on the already-filtered set.
- **LLM** generates an answer strictly from the filtered context.
- **Citations** reference only documents that passed the policy check.

### B. Security evaluation engine

A CLI (`ragfence test`) that runs attack scenarios against a target RAG system (reference implementation or an external adapter) and produces a security report.

Conceptual output:

```
RAGFence Security Report

✓ Cross-tenant isolation
✓ Department isolation
✓ User ACL
✗ Prompt injection resistance
✓ Citation integrity

Score: 82/100
```

The report is deterministic, timestamped, and written as machine-readable JSON alongside the human-readable summary so CI can consume it.

### C. Synthetic benchmark organization: Acme Corp

RAGFence ships a fully synthetic multi-tenant dataset called **Acme Corp**:

- Tenant `acme_corp` with departments: `engineering`, `hr`, `finance`, `legal`, `executive`.
- A second tenant `globex_corp` to exercise cross-tenant isolation.
- Synthetic users mapped to departments and clearance levels, e.g. `engineering_employee` (internal), `finance_analyst` (confidential), `legal_counsel` (restricted).
- Synthetic documents with known classifications and ACLs, including sensitive fixtures such as `finance/payroll/CFO.pdf`.

Deterministic synthetic data matters for security evaluation because:

- Every run has identical ground truth; a failing scenario is a regression, not a random fluke.
- Sensitive content can be designed so leakage is trivially detectable in the answer (e.g. a specific fake salary value).
- The dataset contains deliberate traps (cross-department documents, soft-deleted documents, poisoned documents) that expose naive retrieval.

### D. Attack cases (v0.1 minimum)

1. **Cross-tenant retrieval** — User of tenant A attempts to retrieve documents from tenant B.
2. **Cross-department retrieval** — User in `engineering` attempts to retrieve `finance` documents.
3. **Direct sensitive-data request** — User asks directly for a classified document's contents ("What is the CFO salary?").
4. **Metadata spoofing** — Client supplies forged tenant/department/role parameters; the system must ignore them.
5. **Prompt injection** — User prompt attempts to override system instructions to force document disclosure.
6. **Indirect prompt injection** — A retrieved document contains instructions that attempt to hijack the generation.
7. **Document poisoning** — An attacker-controlled document is engineered to be retrieved and to steer the answer.
8. **Role escalation** — A lower-clearance user attempts to access a higher-classification document.
9. **Deleted-document retrieval** — User attempts to retrieve a soft-deleted document.
10. **Retrieval filter bypass** — User crafts queries/parameters that try to defeat the filter (e.g. negative top-k, wildcard filters, unsorted large ranges).

Each scenario is defined by an `AttackScenario` with an `expected_behavior` ("must block" or "must allow") so evaluation is objective.

---

## 5. Integrations

RAGFence integrates with external RAG systems through an adapter architecture.

| Adapter | Target | v0.1 status |
|---|---|---|
| `generic_http` | Any RAG system exposing HTTP retrieval/answer endpoints | Implemented |
| `langchain` | LangChain-based RAG pipelines | Planned |
| `llamaindex` | LlamaIndex-based RAG pipelines | Planned |
| `custom` | In-process custom implementations via the `RAGAdapter` Python interface | Implemented (library) |

**Explicitly NOT all implemented in v0.1.** The v0.1 adapter contract is `generic_http` and the in-process `RAGAdapter` protocol. `langchain` and `llamaindex` adapters are defined as backlog items; the protocol is designed so they can be added without changing the evaluation engine.

---

## 6. MVP

The v0.1 MVP must allow a developer to:

1. `pip install ragfence`
2. `ragfence init` — scaffold configuration, reference `docker-compose.yml`, and the Acme Corp synthetic dataset.
3. `ragfence test` — run the full local, reproducible security test suite against the reference implementation.

`ragfence test` must run against the reference implementation without any external API keys or network dependency. `ragfence test --adapter generic_http --base-url <url>` must run the same suite against an external RAG system using a minimal HTTP adapter configuration.

---

## 7. Success Metrics

| Metric | Target | Why it matters |
|---|---|---|
| First evaluation < 5 minutes | Fresh install to first `ragfence test` report in under 5 minutes | Adoption depends on zero-friction onboarding |
| Deterministic reproducibility | Identical report for identical input (seed, version, DB state) | Security evidence must be rerunnable |
| Number of attack scenarios | 10 scenario classes in v0.1, growing to 25+ by v0.3 | Coverage breadth is the product's value |
| False positive / false negative tracking | Per-scenario false-positive and false-negative rates reported in the report | Trust requires knowing when the harness lies |
| External adapters contributed | At least 2 community adapters within 6 months of v0.1 | Validates the adapter contract |
| Benchmark usage | Acme Corp dataset used by >= 3 external projects | Confirms the synthetic corpus is credible |

---

## 8. Non-Goals (v0.1)

- **Training LLMs.** RAGFence does not train, fine-tune, or tune models.
- **Being a vector database.** It uses PostgreSQL + pgvector for the reference implementation and never replaces a dedicated store.
- **Replacing corporate IAM.** It defines an authorization contract and a reference identity source (synthetic users), but does not implement enterprise SSO, SCIM, OAuth flows, or identity providers.
- **Being a paid SaaS platform.** RAGFence is self-hostable and local-first; there is no mandatory hosted offering.
- **Solving all of LLM security.** Guardrail-free, model-level safety, data loss prevention for the LLM itself, and policy compliance scanning are out of scope.
- **Frontend for core.** A browser UI is not required for v0.1; the product is CLI and library first. A minimal demo web UI is a future option.

---

## 9. Definitions

| Term | Meaning |
|---|---|
| RAG | Retrieval-Augmented Generation: augmenting an LLM with retrieved document context |
| Authorization context | Server-derived identity attributes used for access decisions |
| ACL | Access Control List: per-document allowed users and groups |
| Deny-by-default | A document is denied unless an explicit policy grants access |
| BYOK | Bring Your Own Keys: user-supplied model/embedding credentials |
