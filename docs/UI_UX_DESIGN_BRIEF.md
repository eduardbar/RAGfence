# RAGFence — UI/UX Design Brief

**Tagline:** Security testing and authorization-aware retrieval for production RAG systems.

**Document status:** v0.1 draft
**Audience:** product, design, engineering
**Scope:** interaction and visual design guidance for the CLI (primary product) and an optional demo web UI (future).

The product is NOT a giant SaaS dashboard. It is a CLI-first security tool. The design goal at every level is the same: **let the user understand what the system tried to retrieve and why it was allowed or blocked.**

---

## 1. Design Principles

1. **Information over decoration.** Every pixel carries data or affordance. No marketing visuals, no gradient flourishes, no cyberpunk clichés.
2. **Security tooling aesthetic.** Technical, disciplined, calm. Feels like a linter crossed with a test runner, not a game.
3. **Deterministic clarity.** The same input renders the same report. No animated mystique where a table will do.
4. **Accessible by default.** WCAG AA contrast; color is never the sole channel — icons/words always accompany it.
5. **Progressive disclosure.** Summary first; drill into evidence on demand.

---

## 2. CLI (Primary Product)

### 2.1 Severity model

The CLI renders four outcome levels (matching `ScenarioOutcome` in `TRD.md`):

| Level | Meaning | Symbol | Color (ANSI 256) |
|---|---|---|---|
| PASS | Scenario behaved as expected; no findings above LOW | `[PASS]` / `✓` | green (118) |
| WARNING | Partial or degraded; LOW/MEDIUM findings, or scenarios skipped | `[WARN]` | amber (214) |
| FAIL | A required expectation was violated | `[FAIL]` | red (196) |
| CRITICAL | Immediate, severe violation (e.g. unauthorized content reached the LLM context) | `[CRIT]` | bright red (196, bold) |

Mapping rules:

- Scenario outcome = worst-severity `SecurityFinding` in that scenario.
- `SecurityFinding.severity` grades findings: LOW, MEDIUM, HIGH, CRITICAL.
- Outcome derivation: no findings → PASS; LOW/MEDIUM → WARNING; HIGH → FAIL; CRITICAL → CRITICAL. A blocked-by-default expectation that leaks (any severity) is always at least FAIL.

### 2.2 Progress / state rendering

- Non-TTY (pipes, CI): plain lines only; no ANSI, no progress bars.
- TTY: a single status line that updates in place:

```
 Running cross-tenant-retrieval ............ 12/25  [PASS]
```

- States: `queued`, `running`, `passed`, `failed`, `error`, `skipped`. Each state has one deterministic symbol and color (see above).
- Long operations (embedding, seeding) render an elapsed counter, never a fake percent.

### 2.3 Report output format

Human-readable, stable, sortable:

```
RAGFence Security Report — run 01HS9XK3A4V...  (suite: default)

✓ Cross-tenant isolation              PASS       12/12
✓ Department isolation                PASS        8/8
✓ User ACL                            PASS        9/9
✗ Prompt injection resistance         FAIL        6/8   ← HIGH finding
✓ Citation integrity                  PASS        5/5

Score: 82/100   Threshold: 80   Result: PASS

Summary: 40 cases, 39 passed, 1 failed, 0 skipped.
Evidence: .ragfence/reports/01HS9XK3A4V/ (JSON + traces)
```

JSON artifact (`--json` or always alongside): one object per `EvaluationCase` with `passed`, `findings` (severity, category, title, evidence), `retrieved` chunk ids, and `latency_ms`.

Exit codes: `0` pass, `1` below threshold or execution failure, `2` usage/config error.

---

## 3. Optional Demo Web UI (Future)

Purpose: a small visual demonstration of the reference implementation's authorization behavior — a diagnostic surface, not a full product dashboard. It ships only as an optional add-on.

### 3.1 Style

- **Dark/light accessible themes**, same component model, tokens swap.
- **Technical and clean**: neutral graphite surfaces, thin borders, monospace for all evidence/traces, restrained use of the accent palette.
- **No cyberpunk cliché**: no neon glow, no scanlines, no garish gradients. Color is semantic, applied to data, not to chrome.

### 3.2 Suggested palette (conceptual)

| Role | Dark | Light |
|---|---|---|
| Background / surface | graphite `#14161A` / `#1B1E24` | off-white `#F7F7F5` / `#FFFFFF` |
| Text primary | off-white `#E8EAED` | graphite `#202124` |
| Text muted | `#9AA0A6` | `#5F6368` |
| Border / divider | `#2A2E35` | `#E0E0DE` |
| Green — safe / allowed | `#34A853` | `#188038` |
| Amber — warning / skipped | `#F9AB00` | `#B06000` |
| Red — violation / denied | `#EA4335` | `#C5221F` |
| Blue — retrieval / AI | `#4285F4` | `#1A73E8` |
| Violet — model / embedding | `#A142F4` | `#8430CE` |

Blues/violets are reserved for the AI/retrieval dimension; green/amber/red are reserved exclusively for security semantics. Contrast for all text pairs meets WCAG AA (>= 4.5:1 normal text).

### 3.3 Typography and spacing

- **Typefaces:** system stack (`Inter`/system-ui) for UI; `JetBrains Mono`/`ui-monospace` for evidence, prompts, traces, and citations.
- **Scale (px):** 12 / 13 / 14 (body) / 16 / 20 / 24. Tabular numbers for scores and latencies.
- **Spacing:** 4px grid; 8/16/24/32 rhythm. Cards use 16px padding, 1px borders.
- **Empty/error states:** explicit; never blank.

### 3.4 Components

**Attack result component** — one scenario, one verdict:

```
┌────────────────────────────────────────────────────────────┐
│ [FAIL] Prompt injection resistance        ✗ 6/8  ·  2 HIGH │
│ Engineering user asked for restricted finance doc.         │
│ The target returned chunk c_42 from finance/payroll/CFO.pdf│
│ ── Details ──▶                                              │
└────────────────────────────────────────────────────────────┘
```

Behavior: collapsed by default; "Details" expands to show the exact prompt, the actor's `AuthorizationContext`, retrieved chunks, and each `SecurityFinding`.

**Authorization context viewer** — the "what am I allowed to see" panel. Columns: tenant, department, classification, groups, source. Shows the server-derived `AuthorizationContext` for the current synthetic user. Any value is clickable to see where it came from (identity → directory lookup → context). This is the component that answers "why was I allowed/blocked" for the *identity* side of the question.

**Retrieval trace** — the "what the system tried to retrieve and why" component. A vertical timeline of the query-time pipeline:

```
query: "What is the CFO salary?"     (actor: engineering_employee)
policy: DENY (department)            → reason: classification CONFIDENTIAL > clearance INTERNAL
filtered search: 0 chunks from 5 candidates
llm: not invoked                    (blocked before context)
```

Each step shows latency. Denied documents render in red with the reason; allowed ones in blue/violet with their score.

**Citations** — under each answer: document title, chunk index, snippet, and a green/red chip confirming the citation passed policy at query time.

**Security report** — the web rendering of the CLI report: scenario table (level, symbol, pass/total, findings), the weighted score, threshold marker, and links to full evidence JSON.

### 3.5 Screen flow (demo only)

1. **Login** — pick a synthetic user (`engineering_employee`, `finance_analyst`, ...). One click; the token is scoped to that identity.
2. **Ask** — a textarea with example questions including the blocked CFO-salary case.
3. **Result** — answer + citations, or `ACCESS DENIED` card; the retrieval trace and authorization context viewer flank it.

The single most important property: a user must be able to reconstruct **what was retrieved, what was blocked, and why** from the trace alone, with no prior knowledge of the codebase.
