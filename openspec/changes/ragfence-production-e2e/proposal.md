# Proposal: RAGFence Production E2E

## Intent
Replace the simulated reference evaluation path with a reproducible PostgreSQL/pgvector-backed reference target and make evaluation results fail closed when identity, retrieval evidence, or positive controls are absent.

## Scope
- Real two-tenant Acme/Globex deterministic fixture, DB identities, documents, ACLs and embeddings.
- Reference adapter using the production DB auth, `RetrievalService`, and `DbVectorStore`.
- Case identity representation for `generic_http`, with explicit configuration and inconclusive outcomes when unavailable.
- Evaluation matrix with allow and block controls; non-passing/inconclusive semantics that prevent all-block targets from passing.
- Working CLI lifecycle: `init --up`, `test --output`, `demo --up`, adapter check.
- CI PostgreSQL/pgvector integration and documentation aligned to the actual commands.

## Non-goals
- Deploying a hosted service, publishing packages, pushing or committing.
- Adding real vendor LLM calls; deterministic fake generation remains an explicit test/reference generation provider.

## Success criteria
1. Reference CLI evaluation uses a migrated, seeded PostgreSQL + pgvector DB rather than `_ReferenceTarget`.
2. Acme and Globex actors are persisted and DB-resolvable; cross-tenant and positive-control retrieval execute the real retrieval path.
3. A target without actor representation or positive controls reports INCONCLUSIVE and cannot pass a threshold.
4. CLI/workflow/docs expose only executable contracts.
5. CI invokes DB integration tests with pgvector.
