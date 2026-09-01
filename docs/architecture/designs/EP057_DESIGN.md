# EP-057 — Memory Optimization — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN APPROVED (D1-D4 all Owner-approved). STEP 2
— COMPLETE. STEP 3 — AUDIT PASSED WITH FINDINGS (three non-blocking
findings, zero blocking). STEP 4 — COMPLETE (all three findings
closed; no Owner Decision was required to proceed).**

**Owner Decisions D1-D4 (Section 20) are all APPROVED, exactly as
recommended in this document, with no modification.** Candidate A
(Section 5) is the approved v1 scope for EP-057, and Sections 6-17's
provisional architecture is the approved architecture — see the Owner
Approval Checklist at the end of this document for the approved value
of each decision, and `docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md`
for the STEP 3 audit and STEP 4 remediation record.

This document's original STEP 1 text (Sections 0-20 below) is
preserved verbatim below, exactly as first approved — nothing has
been edited or reworded to match what STEP 2/3/4 actually did. Only
this status block and the Owner Approval Checklist at the end were
added, at STEP 4, to record final disposition — mirroring the
precedent `EP055_DESIGN.md`/`EP056_DESIGN.md` already established.

---

## 0. How this document relates to EP-054, EP-055, and EP-056

EP-054, EP-055, and EP-056 each began with a roadmap line whose only
content was a title and Phase 9's shared, one-sentence, five-EP-wide
goal. Each STEP 1 document disclosed this gap explicitly rather than
inventing scope, derived candidate interpretations from
already-existing, already-inspected architecture, and asked the owner
to choose among them via an Owner Decision before any provisional
architecture was treated as authorized.

**EP-057 is in the identical situation, confirmed by the same
exhaustive-search method (Section 2).** "EP-057 Memory Optimization"
has no functional specification anywhere in the repository beyond its
title and the same Phase 9 goal EP-054/EP-055/EP-056 already shared.
This document follows the identical methodology: Section 2 is a
verbatim inventory of every reference found, Section 3 grounds
candidate interpretations in already-existing architecture, and
Section 20's Owner Decisions ask the owner to choose before Sections
6-17's provisional architecture is treated as more than a starting
proposal.

**One material difference from all three prior EPs, found during
discovery (Section 3.4):** EP-057 is the first of the four "bare
title" EPs where the strongest textual anchor is not a docstring
naming the EP's own concept (as EP-056's "reserved for the future
Capability Registry" did), but a **fully implemented, fully tested,
currently zero-caller method pair** — `CompressionEngine.
compress_query()` / `compress_semantic_results()` (EP-027) — whose own
docstring already states it exists specifically to compress the
results of a semantic search over Long-Term Memory (EP-025) and
Knowledge Base (EP-024) content. This document treats that discovery
as strong evidence, not as an automatic conclusion — per this task's
explicit instruction, Section 5 evaluates it against three other
candidates on equal terms before recommending it.

---

## 1. Metadata

- **Engineering Package:** EP-057 — Memory Optimization
- **Phase:** Phase 9 — Intelligence (`docs/architecture/JARVIS_ROADMAP.md`
  line 897; `docs/engineering/ENGINEERING_GUIDE.md` lines 163-168:
  "Improve reasoning and autonomous decision making.")
- **Predecessors:** EP-054 Self Reflection — COMPLETE (AUDIT PASSED
  WITH FINDINGS); EP-055 Prompt Optimizer — COMPLETE (PASS AFTER
  REMEDIATION); EP-056 Capability Learning — COMPLETE (PASS AFTER
  REMEDIATION). All three followed the identical "bare title, no
  spec" discovery methodology this document also follows.
- **Successor (same phase):** EP-058 Autonomous Planning.
- **Foundational, already-complete dependencies (different phases):**
  EP-013/EP-023 Memory & Context Manager (`MemoryStore`,
  `MemoryManager`, `MemoryService`); EP-016 Conversation Engine
  (`Conversation`, `ConversationManager`); EP-018/EP-018.2/EP-018.5/
  EP-018.6 Context Loader, Smart Context Selection, Unified Prompt
  Budget, Conversation Budget Enforcement (`ContextManager`,
  `ContextLoader`); EP-024 Knowledge Base; EP-025 Long-Term Memory
  (`LongTermMemoryManager`, `LongTermMemoryService`); EP-026 Semantic
  Search (`SemanticEngine`); EP-027 Context Compression
  (`CompressionEngine`, `CompressionManager`, `CompressionService`).
- **This document's scope:** STEP 1 only — repository discovery,
  scope clarification, architecture proposal (contingent on Owner
  Decision D1), and Owner Decision preparation. No code, test,
  configuration, dependency, or Bootstrap file has been created or
  modified as part of producing this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP057_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. What the repository actually says about EP-057 (verbatim inventory)

Every reference to EP-057 or "Memory Optimization" found anywhere in
the repository, by direct, exhaustive search of `docs/`,
`AI_GENERATION_STANDARD.md`, `CHANGELOG.md`, and `src/`:

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` line 897 (Phase 9 checklist) | `EP-057 Memory Optimization` — a bare title, no elaboration |
| `docs/architecture/JARVIS_ROADMAP.md` lines 214-216 ("Next Engineering Package" note, added by EP-056 STEP 4) | `**Next Engineering Package: EP-057 Memory Optimization — NOT STARTED.** No EP-057 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/BACKLOG.md` lines 13-18 ("Next Engineering Package" section, added by EP-056 STEP 4) | `### EP-057 — Memory Optimization` / `**NOT STARTED.** Per docs/architecture/JARVIS_ROADMAP.md's Phase 9 sequencing, EP-057 (Memory Optimization) is the next Engineering Package after EP-056's completion. No design, research, or implementation work has begun.` — same pointer, same lack of elaboration |
| `CHANGELOG.md` line 197 | References EP-057 only as "the next, not-started Engineering Package" in the EP-056-completion entry — a status note, not a spec |
| `docs/architecture/designs/EP054_DESIGN.md` line 42 | Lists EP-057 Memory Optimization only as a successor EP in its own metadata section — does not define EP-057's scope |
| `docs/architecture/designs/EP055_DESIGN.md` lines 78/321/797 | Lists EP-057 as a successor EP in scope-boundary reasoning; line 797 explicitly records as an *open question* "Whether a future EP-056/057/058 will expect Prompt Optimizer's output ... in a specific, machine-readable format" and answers "no such requirement exists ... today" |
| `docs/architecture/designs/EP056_DESIGN.md` lines 66-67, 770-777 | Lists EP-057 as a same-phase successor; Section 19 explicitly records, as an unresolved question, "Whether a future EP (EP-057 Memory Optimization, EP-058 Autonomous Planning) will expect Capability Registry's output in a specific, machine-readable format" — answered "no such requirement exists anywhere in the repository today" |
| `docs/engineering/ENGINEERING_GUIDE.md` (Phase 9 section, lines 163-168) | `## Phase 9 — Intelligence` / `Improve reasoning and autonomous decision making.` / `Engineering Packages:` / `EP-054 … EP-058` — a **phase-level** goal shared across all five Phase-9 EPs, not an EP-057-specific one |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, every EP-001…EP-056 design/audit document except the cross-references above, `src/`) | **Zero** additional mention of EP-057, "Memory Optimization," or any synonym of it |

**Conclusion (identical in kind to EP-054's, EP-055's, and EP-056's
own Section 2 conclusions):** the repository establishes *that*
Memory Optimization is next, and *that* it belongs conceptually to
"Intelligence," but establishes **no concrete behavior, input,
output, trigger, metric, or user interface** for EP-057 by that name.
No prior EP's design document names EP-057 as an already-anticipated
consumer of anything it built — unlike EP-056's discovery of
`append_capabilities()`'s docstring literally naming "the future
Capability Registry," no source file anywhere names "Memory
Optimization" or an EP-057-specific concept. Section 3, however,
identifies a strong, independently-discovered *functional* anchor
(distinct from a naming anchor): a fully-built, fully-tested,
zero-caller code path that already does something a plain-language
reading of "optimizing memory" would recognize.

---

## 3. Relevant existing architecture (grounds for the candidate interpretations in Section 5)

### 3.1 The Memory & Context Manager (EP-013/EP-023) — raw key/value memory, already TTL- and cap-bounded

`src/core/memory/memory_store.py`'s `MemoryStore` is a thread-safe,
namespaced `MemoryEntry` store with TTL support
(`MemoryEntry.is_expired()`), lazily purged on `get()`/`list()`/
`export_snapshot()`/`clear()` (`_purge_expired()`). `MemoryService`
(`src/services/memory_service.py`) enforces `memory.max_entries`
(default 10000) as a **hard write-reject** at `set()` time
(`"Memory max_entries exceeded"`, line 236) — there is no eviction
policy (LRU, oldest-first, or otherwise); a caller at the cap must
delete something manually before writing again.
`MemoryPersistence` (`src/core/memory/memory_persistence.py`) runs a
background auto-save loop (`memory.auto_save_interval`, default 60s)
that calls `MemoryStore.export_snapshot()`, which incidentally also
calls `_purge_expired()` as a side effect — so **expired entries are
proactively swept only when `memory.persistent` is `true`** (the
default); if persistence is disabled, expired entries are purged only
on next direct access. Confirmed: `grep -rn "max_entries" src/` finds
no eviction logic, only the reject-and-message path above.

### 3.2 The Conversation Engine (EP-016) — a dead configuration key, confirmed

`ConversationManager.truncate_strategy()`
(`src/core/ai/conversation_manager.py` line 110) reads and returns
`conversation.truncate_strategy` (default `"oldest"`, confirmed
present in `config/config.yaml` line 593) — but **no caller anywhere
in the repository reads this method's return value**
(`grep -rn "truncate_strategy" --include="*.py" .` finds it defined
once, documented in three docstrings, and stamped into
config-fixture-building test helper strings twenty-five times across
prior EPs' test suites, but never read as a live value by any
production code path). `Conversation._truncate_locked()`
(`src/core/ai/conversation.py` lines 273-283) enforces `max_messages`
by unconditionally dropping the oldest messages first — this is
correct behavior for the *only* strategy that has ever been
implemented, but it means `truncate_strategy` is a **configuration
key with no effect**: setting it to any value other than `"oldest"`
changes nothing. This is a different flavor of "dead seam" than
EP-056's docstring-anchored `append_capabilities()` — here the
gap is a live, already-shipped config surface whose promised
knob does not turn anything.

### 3.3 The Context Loader (EP-018.5/EP-018.6) — an already-solved, character-budget approach to conversation-history sizing

`prompt.max_prompt_size` (default 32000, `config/config.yaml` line
647) is, per its own comment, "the ONE prompt-size authority in the
project." `ContextManager` (`src/core/ai/context_manager.py`) is
constructed with `document_budget`/`conversation_budget` callables
sourced from `PromptManager`, and forwards both, unchanged, to
`ContextLoader`, which already enforces a character-based budget on
Conversation Context specifically (EP-018.6 "Conversation Budget
Enforcement", module docstring lines 42-48). **This means conversation
history is already size-bounded today, by two independent mechanisms
operating at two different layers:** `Conversation.max_messages`
(a message-count cap, EP-016) and `ContextLoader`'s
`conversation_budget` (a character-count cap applied when composing a
prompt, EP-018.6). Neither mechanism deduplicates or compresses
content — both are pure truncation (drop oldest messages / drop
oldest characters). This is confirmed, working, in-production
behavior — not a gap — and is recorded here so Section 5's candidates
are not proposed in ignorance of it: any candidate that touches
conversation-history sizing must explain how it differs from, or
composes with, this already-shipped truncation, not silently
duplicate it.

### 3.4 Context Compression (EP-027) — a fully built, fully tested, semantic-memory-aware compression path with zero production callers

`src/core/context_compression/compression_engine.py`'s
`CompressionEngine` exposes four public methods:
`compress_text()`, `compress_chunks()`, `compress_semantic_results()`,
and `compress_query()`. The last two are, per the class's own
docstring (lines 85-91), the pipeline for **"Semantic Search results
-> deduplicate -> preserve ordering -> enforce limits ->
CompressionResult."** `compress_query()` internally calls
`SemanticEngine.search()` (EP-026), which itself searches over
Knowledge Base (EP-024) and Long-Term Memory (EP-025) records
(confirmed: `SemanticEngine.__init__` takes `knowledge_service` and
`long_term_memory_service`, `src/bootstrap.py` line ~742).

**Confirmed by direct, exhaustive search
(`grep -rn "compress_query\|compress_semantic_results" --include="*.py" .`)
that these two methods have exactly one caller each: EP-027's own test
suite (`tests/EP027/test_context_compression.py`).** `CompressionService`
(`src/services/context_compression_service.py`, the CLI-facing layer
every command in `ContextCompressionModule` goes through) exposes
only `analyze(text)` and `compress(text)` — both routed to
`compress_text()`. **`compress_query()` and `compress_semantic_results()`
are not reachable from `ContextCompressionModule`, `CompressionService`,
`AIService`, or any Bootstrap wiring.** `src/bootstrap.py`'s own
comment at the EP-027 construction site (lines 772-774) states this
explicitly and un-ambiguously: *"reaching Semantic Search only through
SemanticEngine's public `search()` method (optional -- used only by
`compression`'s future callers via `compress_query()`, never by the
CLI commands wired here)"* — this is not this document's inference;
it is a direct quotation of an existing code comment, written when
EP-027 was built, that names "future callers" as the reason the method
exists at all.

**A second, load-bearing fact this document verified directly:**
`CompressionEngine` is *already* constructed in `Bootstrap` with a
live `SemanticEngine` instance whenever Semantic Search is available
(`src/bootstrap.py` lines 783-792,
`compression_engine = CompressionEngine(manager=compression_manager,
semantic_engine=semantic_engine_for_compression)`). This means
`compress_query()` is not merely implemented — it is **already wired
and already callable in a running Bootstrap** the moment any caller
reaches it through the engine; no Bootstrap or construction-ordering
change (unlike EP-056's Section 3.8 finding) is required to make it
reachable. Only the Service/Module layer is missing.

### 3.5 EP-027's own architectural boundary — a real constraint on any candidate that reuses it

`src/core/context_compression/__init__.py`'s module docstring states
Context Compression "has no dependency on any AI Provider, the Prompt
Engine, the RAG Engine (EP-022), Conversation Engine, Planner,
Reflection, Browser Automation, Tool Calling, or any future Agent
Framework component. It may use only the public APIs of Semantic
Search (EP-026), Knowledge Base (EP-024), and Long-Term Memory
(EP-025)." This is confirmed unmodified
(`compression_engine.py`'s own docstring, lines 13-25, repeats the
identical restriction). **This constraint rules out any candidate
that would have Context Compression itself reach into
`ConversationManager`/`Conversation`** (Section 3.2/3.3) — the
restriction runs one way (Context Compression must not depend on the
Conversation Engine), so a candidate where `ConversationManager`
instead depends on `CompressionService` (the reverse direction) would
not violate it, but such a candidate is still a cross-cutting change
touching a second, independent, already-shipped subsystem (EP-016)
and is evaluated on those terms in Section 5's Candidate C.

### 3.6 Long-Term Memory (EP-025) — active/archived lifecycle, no compaction or deduplication of its own

`src/core/long_term_memory/long_term_manager.py`/`long_term_provider.py`
implement `store`/`get`/`update`/`archive`/`delete`/`clear`/`list`/
`stats`, with a two-state lifecycle (`STATUS_ACTIVE`/`STATUS_ARCHIVED`)
persisted as reserved metadata keys inside each record. Confirmed by
direct search (`grep -n -i "dedup\|compact\|prune\|evict\|optimiz"
src/core/long_term_memory/*.py src/services/long_term_memory_service.py`):
**zero matches.** Long-Term Memory has no automatic archival policy
(archiving is only ever a manual, single-record `ltm archive <id>`
action), no deduplication of near-identical stored memories, and no
compaction of archived records. This is a real, confirmed absence —
but, per the same reasoning EP-055's Section 3.5 and EP-056's Section
3.5 already applied to their own structurally similar gaps, building
an archival policy, a deduplication heuristic, or a compaction scheme
from nothing would require inventing a policy this document has no
repository evidence to derive; it is recorded as Candidate D
(Section 5) and not recommended for v1.

### 3.7 `CommandRouter` / `CommandModule` precedent — confirmed still current

Every skill (`desktop`, `browser`, `file`, `vision`, `reflect`,
`prompt`, `plugin`, `capability`, and ~39 others as of EP-056's
completion) is a `CommandModule` registered with the unmodified
`CommandRouter.dispatch()`. Confirmed byte-identical to its state at
EP-056's completion. `compression` and `ltm` are both existing
namespaces already following this pattern
(`ContextCompressionModule`, `LongTermMemoryModule`) — any EP-057
candidate that needs a new user-facing action can extend one of these
two existing namespaces rather than introduce a new one, unless a
new namespace is independently justified (Section 4/Section 6.1's
command-surface decision).

### 3.8 No usage/outcome tracking or adaptive infrastructure exists anywhere (confirmed unchanged since EP-056)

Direct, exhaustive search
(`grep -rln -i "success_rate|usage_stat|telemetry|analytics|track.*usage" src/`)
confirms, unchanged from EP-056's own Section 3.5 finding, that no
component records whether a memory entry, conversation, or long-term
record is "used frequently" or "valuable" by any historical signal.
An interpretation of "Optimization" that means *adaptive* pruning
(e.g., "forget memories that are rarely accessed") has zero existing
infrastructure to build on and would require inventing an access-
frequency metric and a forgetting policy from nothing.

---

## 4. What this document does NOT propose (scope boundaries, stated up front)

- **No adaptive, usage-based, or access-frequency-driven memory
  pruning of any kind** (Section 3.8) — no metric, no persistence
  schema, and no forgetting policy is proposed; this is Candidate B
  (Section 5), explicitly rejected for v1.
- **No redesign of `MemoryStore`'s TTL/eviction model or
  `memory.max_entries` enforcement** (Section 3.1) — recorded as
  Candidate D-equivalent evidence and a possible, smaller future
  direction, not built here.
- **No new `truncate_strategy` implementation for the Conversation
  Engine** (Section 3.2) — recorded as Candidate C, evaluated and not
  recommended for v1 (Section 5) because it requires modifying
  `Conversation`/`ConversationManager`, both owned by EP-016, for a
  cross-cutting change with a materially larger blast radius than
  Candidate A.
- **No modification of Context Compression's own architectural
  boundary** (Section 3.5) — `CompressionEngine`/`CompressionManager`/
  `CompressionProvider`/`compression_result.py` are treated as fixed;
  this document's recommended candidate is additive to the Service/
  Module layer only.
- **No modification of the EP-013/023 Memory & Context Manager, the
  EP-016 Conversation Engine, the EP-024 Knowledge Base, the EP-025
  Long-Term Memory system, or the EP-026 Semantic Search engine's
  existing public APIs.** All are treated as fixed; EP-057 is
  additive to them, exactly as EP-054/055/056 were additive to the
  components they each reused.
- **No new AI-provider call of any kind** — none of Section 5's
  candidates require one (Section 7).
- **No cross-EP scope creep.** This document does not redesign or
  re-scope EP-054, EP-055, EP-056, or EP-058.

---

## 5. Candidate interpretations of "Memory Optimization" (grounds for Owner Decision D1)

Each candidate is derived from an existing, already-inspected part of
the repository (Section 3), not invented from outside knowledge of
what "memory optimization" might mean in the abstract. None is
authorized; Owner Decision D1 (Section 20) asks the owner to choose
one (or explicitly reject all of them and redirect this document).
Per this task's explicit instruction, `compress_query()`'s
zero-caller status (Section 3.4) is treated as evidence to be weighed
against the other three candidates, not as an automatic conclusion —
each candidate below is evaluated on groundedness, blast radius, and
risk on its own terms.

### Candidate A — Expose EP-027's semantic-memory compression pipeline as an on-demand "optimize this memory retrieval" capability (recommended)

Add a `query` action to the existing `compression` `CommandModule`
(and a matching `query()` method on `CompressionService`) that calls
the already-built, already-tested, already-wired
`CompressionEngine.compress_query()`: given a natural-language query,
it runs `SemanticEngine.search()` over Knowledge Base/Long-Term
Memory content, then deduplicates and size-bounds the results via the
active `CompressionProvider`, returning a `CompressionResult` for
inspection — finally giving `compress_query()`/
`compress_semantic_results()` their first real caller outside EP-027's
own test suite.

**Why recommended:** (1) it is the only candidate grounded in a
component that is *already fully implemented, already tested, and
already wired end-to-end in Bootstrap* (Section 3.4) — the smallest
possible implementation gap of any candidate considered, since
`CompressionEngine.compress_query()` requires no new business logic,
only a new Service method and a new CLI action forwarding to it,
mirroring `analyze()`/`compress()`'s own existing one-line-forward
pattern (Section 6.2). (2) It requires **zero Bootstrap change**
(Section 3.4's second finding) and **zero configuration change**
(reuses `context_compression.*`'s existing `enabled`/
`max_context_characters`/`max_chunks`/`deduplicate` knobs unchanged).
(3) It directly answers a plain-language reading of "Memory
Optimization": it makes retrieval *from* Long-Term Memory/Knowledge
Base more efficient (deduplicated, size-bounded) for a downstream
consumer, which is a narrower but still faithful reading of
"optimization" than Candidates B-D below, none of which have
comparably strong, already-built infrastructure to stand on. (4) It
respects Section 3.5's architectural boundary without modification —
Context Compression's own restriction against depending on the
Conversation Engine is never touched, since this candidate never
approaches `ConversationManager` at all.

### Candidate B — Usage/access-frequency-based adaptive memory pruning ("forgetting") (rejected as a v1 candidate)

A literal reading of "Optimization" as *reducing footprint over time*:
track how often each `MemoryEntry`/long-term record is
read/searched/matched, and archive, expire, or delete entries that
fall below some usage threshold. **This document does not recommend
this candidate for v1:** Section 3.8 already confirmed zero existing
infrastructure of any kind for this (no access-frequency counter, no
persistence schema for one, no pruning policy) — building one from
nothing is exactly the category of invented, ungrounded scope
EP-055's own Candidate D and EP-056's own Candidate B were each
already declined for the identical reason. Recorded here to be
explicitly rejected, not silently omitted — the owner may of course
choose it anyway (Owner Decision D1), in which case this document
would need substantial revision to design a metric/persistence/policy
scheme first.

### Candidate C — A real, second `conversation.truncate_strategy` implementation (rejected as a v1 candidate, but the second-most-grounded)

Address Section 3.2's confirmed dead configuration key directly:
implement a second, alternative truncation strategy (e.g.,
`"compress"`, which would deduplicate similar messages before
dropping the oldest, versus the existing hardcoded `"oldest"`), read
via `ConversationManager.truncate_strategy()`'s already-existing
(but currently unconsumed) return value. **This document does not
recommend this candidate for v1:** unlike Candidate A, it requires
modifying `Conversation._truncate_locked()` and/or
`ConversationManager` (Section 3.2) — both owned by EP-016, an
already-complete, already-audited subsystem this document would
otherwise leave untouched — and, per Section 3.5, if such a strategy
wanted to reuse Context Compression's deduplication logic it would
need `ConversationManager` to take a new dependency on
`CompressionService`, a larger and more cross-cutting change than
Candidate A's purely additive Service/Module extension. It is also a
narrower fix (one dead config key) than Candidate A's broader
"give an entire fully-built subsystem its first caller." Recorded as
the strongest fallback if the owner specifically wants EP-057 to
close a *confirmed dead configuration key* rather than expose an
*unused-but-live* capability.

### Candidate D — Long-Term Memory archival/deduplication policy (rejected as a v1 candidate)

Add automatic archival (e.g., archive records untouched for N days)
or near-duplicate detection/merging directly inside
`LongTermMemoryManager`/`LongTermMemoryService` (Section 3.6).
**This document does not recommend this candidate for v1:** Section
3.6 already confirmed zero existing infrastructure for either
capability (no access-recency tracking, no similarity-based merge
logic beyond what Semantic Search already does for *retrieval*, not
*storage*), and it would require modifying EP-025's own core files
(`long_term_manager.py`, `long_term_provider.py`) — an already-
complete subsystem — rather than being purely additive, unlike
Candidate A. It shares Candidate B's "invent a policy from nothing"
problem, scoped to Long-Term Memory specifically instead of Memory
generally. Recorded here to be explicitly rejected, not silently
omitted.

---

## 6. Proposed architecture (contingent on Owner Decision D1 = Candidate A)

**Everything in this section and Sections 7-19 is provisional,
written against Section 5's recommended Candidate A, and is not
authorized until Owner Decision D1 (Section 20) is explicitly
approved.** If the owner selects a different candidate, or rejects
all of them, this document's STEP 1 must be revised before STEP 2 can
begin.

### 6.1 Command-surface decision (Owner Decision D4)

Two existing namespaces are plausible hosts for a new "query and
compress my memory" action: the existing `compression` namespace
(Section 3.7, `ContextCompressionModule`) or the existing `ltm`
namespace (`LongTermMemoryModule`). This document recommends
**extending `compression`** with a new `query` action
(`compression query "<text>"`), for three grounded reasons: (1) the
underlying method being exposed, `compress_query()`, already lives on
`CompressionEngine` and is already injected into `CompressionService`
— extending `ltm` instead would require `LongTermMemoryModule` to
take a new dependency on `CompressionService` it does not have today,
a larger change for the same outcome; (2) `compression query` reads
naturally alongside the already-existing `compression analyze`/
`compression compress` actions (same namespace, same verb-plus-text
argument shape); (3) it mirrors `semantic search "<query>"`'s own,
already-established naming convention (`SemanticModule`, Section
3.7) for a query-shaped CLI action, so a user already familiar with
`semantic search` finds `compression query` unsurprising. Recorded as
Owner Decision D4 in case the owner has a naming preference not
evidenced in the repository today.

### 6.2 No new backend Protocol

Like EP-054's, EP-055's, and EP-056's own Candidate A, this candidate
introduces no new external I/O surface — it exposes an already-built,
already-tested method (`CompressionEngine.compress_query()`) through
one new Service method and one new CLI action. No new Protocol,
Provider, Manager, or Engine is proposed.

### 6.3 Command/action design (provisional)

| Action | Arguments | Description |
|---|---|---|
| `compression query` | `<natural-language query text>` | (New, Candidate A) Run `CompressionEngine.compress_query(query)`: perform a semantic search over Knowledge Base/Long-Term Memory content (EP-026), then deduplicate and size-bound the results via the active `CompressionProvider` and the existing `context_compression.*` limits. Returns the same `CompressionResult` shape `compression compress` already returns (original/compressed chunk and character counts, deduplicated count, truncated flag, joined text) for inspection. Read-only with respect to Memory/Long-Term Memory/Knowledge Base — no write, archive, or delete of any record. |

No other action is proposed for v1. `compression help`/`status`/
`providers`/`use`/`analyze`/`compress`/`limits` are unchanged.

### 6.4 Integration points

- `CompressionEngine.compress_query()` (already-existing, unmodified,
  EP-027) — the entire new capability is one additional call site
  into this already-built method.
- `SemanticEngine.search()` (already-existing, unmodified, EP-026) —
  reached only indirectly, through `compress_query()`'s own existing
  internal call; `CompressionService`/`ContextCompressionModule` gain
  no new direct dependency on `SemanticEngine`.
- **No** integration with `ConversationManager`/`Conversation`
  (Section 3.5's architectural boundary) — Candidate A never
  approaches the Conversation Engine.
- **No** integration with `AIService.ask()` — `compression query` is
  an on-demand, explicitly-invoked CLI action, never wired into the
  automatic per-request pipeline, mirroring EP-056's own Candidate A
  reasoning for `capability list`/`capability inject`.
- **No** new integration with `MemoryStore`/`MemoryService` (EP-013/
  023) — Candidate A optimizes retrieval from Long-Term Memory/
  Knowledge Base specifically (the two sources `SemanticEngine`
  already searches), not the raw namespaced key/value `MemoryStore`,
  which `SemanticEngine` does not index today (confirmed: `grep -n
  "MemoryStore\|MemoryService" src/core/semantic/*.py` finds no
  match). Recorded as a real scope boundary, not an oversight.
- **No** Bootstrap change (Section 3.4) — `CompressionEngine` is
  already constructed with a live `SemanticEngine` wherever Semantic
  Search is available; `compress_query()` raises the already-existing
  `SemanticSearchUnavailableError` cleanly when it is not (e.g.,
  Embedding Engine unavailable this run), exactly the same soft-
  dependency behavior EP-027 already established for its own
  construction (Section 3.4/bootstrap.py comment).

---

## 7. Security model (provisional, Candidate A)

- Gated by the already-existing `context_compression.enabled` flag
  (re-checked by `CompressionManager`/`CompressionEngine` on every
  call, unchanged) — no new gate is introduced. `compression query`
  additionally inherits `compress_query()`'s own existing
  `SemanticSearchUnavailableError` behavior when Semantic Search
  itself is unavailable this run (Section 6.4) — this is not a new
  security control, only the existing soft-dependency failure mode
  surfaced through a new CLI action.
- **No AI-provider call exists anywhere in Candidate A** — like
  EP-056's own Candidate A, this composes and searches only
  already-declared, locally-stored content and never calls
  `AIProvider.ask()`. No new AI-provider-cost/privacy gate is needed.
- **No new filesystem write surface** — `compress_query()` is
  read-only with respect to Knowledge Base/Long-Term Memory/Memory;
  it performs no store/update/archive/delete of any record.
- **Information-disclosure consideration:** `compression query`
  discloses Long-Term Memory/Knowledge Base content matching the
  given query, deduplicated and size-bounded. This is the same class
  of information `ltm list`/`ltm info <id>`/`semantic search` already
  disclose today (all three already read the same underlying
  Long-Term Memory/Knowledge Base records without any additional
  gate beyond their own subsystem's `enabled` flag) — `compression
  query` discloses nothing that `semantic search` does not already
  disclose in a less-processed form. Recorded explicitly so the owner
  can weigh in if they read it differently (Owner Decision D3,
  Section 20), mirroring EP-056's own Owner Decision D3 pattern.
- **No shell/code execution, no network call** — `compression query`
  introduces no new I/O surface beyond the one already-existing
  method call named in Section 6.4.

---

## 8. Configuration (provisional, Candidate A)

**No new configuration key is proposed.** `compression query` reuses
`context_compression.enabled`/`default_provider`/
`max_context_characters`/`max_chunks`/`deduplicate` (all already
present in `config/config.yaml`, lines 849-864) and
`semantic.top_k`/`similarity_threshold` (already present, lines
831-847, as `compress_query()`'s own already-existing defaults for
its optional `top_k`/`threshold` parameters). This is a stronger
"zero new configuration" position than any of EP-054/055/056's own
Candidate A, none of which were fully config-free.

---

## 9. Dependencies

**No new third-party dependency is anticipated for Candidate A.**
`CompressionEngine`/`CompressionService` are already-installed,
already-imported, unmodified components; forwarding one additional
call requires only what EP-027 already depends on.

---

## 10. Error handling (provisional, Candidate A)

- `compression query` reuses `compress_query()`'s own, already-
  existing, already-tested exception surface, exactly as
  `CompressionService.compress()` already reuses `compress_text()`'s
  (Section 6.2's mirrored pattern): `SemanticSearchUnavailableError`
  (Semantic Search not configured this run), `EmptyContextError`
  (the search returned no results), `NoCompressionProviderSelectedError`
  (subsystem disabled or no provider selected), `CompressionEngineError`
  (the semantic search itself failed), `CompressionProviderError`
  (the active provider failed to compress). All five are already-
  existing, already-tested exception types (Section 3.4/EP-027) —
  none is new, and none is re-implemented, exactly as
  `EP055_DESIGN.md` Section 10 and `EP056_DESIGN.md` Section 10
  already established as the project's convention.
- If `context_compression.enabled` is `false`, or Semantic Search is
  unavailable this run, `compression query` returns a clear,
  non-crashing failure message via `CommandResult(success=False,
  ...)`, matching every other action's convention (mirroring
  `compression compress`'s own existing error path exactly).

---

## 11. Cross-platform considerations

None anticipated — Candidate A performs no OS-specific I/O of any
kind (no device, no external binary, no filesystem write).

---

## 12. Testing strategy (provisional, Candidate A)

Mirrors the now-four-times-established convention
(`EP054_DESIGN.md`/`EP055_DESIGN.md`/`EP056_DESIGN.md` Section 12):

- **`tests/EP057/test_memory_optimization.py`** (primary, always-run
  suite):
  - Protocol/argument-shape tests (`compression query` with zero
    arguments returns a usage message, matching `compression
    compress`'s own existing argument-count check).
  - `context_compression.enabled` gate test (disabled rejects with
    zero calls to `SemanticEngine`).
  - `SemanticSearchUnavailableError` path test — `CompressionService.
    query()` constructed with a `CompressionEngine` that has no
    `SemanticEngine`, asserting a clean, non-crashing `CommandResult`
    failure (mirrors `compress_query()`'s own already-existing
    `_test_engine_compress_query_without_semantic_engine_raises`
    unit test, EP-027, at the Service/Module layer instead of the
    Engine layer).
  - Positive-path test using the **real, unmodified**
    `CompressionEngine`/`SemanticEngine`/a temporary-directory-backed
    Knowledge Base (mirroring EP-027's own
    `_test_engine_compress_query_with_real_semantic_engine`, and
    EP-055's/EP-056's own precedent of preferring one real,
    non-fake integration test over an all-fake alternative for the
    one genuine cross-subsystem integration point a candidate
    touches): store a known fact, query for it, assert the returned
    `CompressionResult` contains it.
  - Empty-results test (`EmptyContextError`) — query text guaranteed
    to match nothing, asserting a clear, non-crashing failure message.
  - `CommandRouter` dispatch-equivalence test, mirroring
    `EP054_DESIGN.md`'s/`EP055_DESIGN.md`'s/`EP056_DESIGN.md`'s own
    `_test_command_router_dispatch_matches_direct_execute`.
  - Bootstrap wiring test — `compression query` reachable through the
    already-registered `compression` namespace with zero Bootstrap
    changes (asserts Section 6.4's "no Bootstrap change" claim is
    genuinely true, not merely argued).
- **No AI-provider-related test tier is needed at all** — Candidate A
  makes no AI-provider call (Section 7), so no
  Owner-Decision-D8-equivalent question about real-provider
  integration testing arises for this EP.

---

## 13. Regression strategy

Full regression suite (`test all`) re-run exactly as in every prior
EP's STEP 2/3, expecting the same, already-disclosed pre-existing
figures plus the new EP-057 suite passing cleanly, with zero change
to any other suite's result — in particular, zero change to any
existing EP-025 Long-Term Memory, EP-026 Semantic Search, or EP-027
Context Compression behavior, since Candidate A adds no code to
`long_term_manager.py`/`long_term_provider.py`/`semantic_engine.py`/
`semantic_provider.py`/`compression_engine.py`/`compression_manager.py`/
`compression_provider.py`/`compression_result.py` at all (Section 14).

---

## 14. File-scope matrix (provisional, Candidate A — NOT authorized until D1 is approved)

### CREATE

- `tests/EP057/__init__.py`, `tests/EP057/test_memory_optimization.py`.

### MODIFY

- `src/services/context_compression_service.py` — additive only: one
  new `query(text: str, top_k: int | None = None, threshold: float |
  None = None) -> QueryOutcome` method (a new, `CompressOutcome`-
  shaped frozen dataclass), forwarding to
  `self._engine.compress_query(...)` exactly as `compress()` already
  forwards to `compress_text()`. No existing method's signature,
  behavior, or return type changes.
- `src/modules/context_compression_module.py` — additive only: one
  new `"query"` entry in `self._actions`, one new `_query()` handler
  (formatting a `CommandResult` from `QueryOutcome`, mirroring
  `_compress()`'s own existing formatting exactly), and one new line
  in `HELP_TEXT`. No existing action's behavior changes.
- `src/modules/test_module.py` — additive only: one new import
  registering `tests.EP057.test_memory_optimization`.

### DO NOT MODIFY

- `src/core/context_compression/compression_engine.py`,
  `compression_manager.py`, `compression_provider.py`,
  `compression_result.py`, `src/core/context_compression/__init__.py`
  — **zero changes**; `compress_query()`/`compress_semantic_results()`
  are called, never modified.
- `src/core/semantic/`, `src/services/semantic_service.py`,
  `src/modules/semantic_module.py` — **zero changes**;
  `SemanticEngine.search()` is reached only indirectly, through
  `compress_query()`'s own existing internal call.
- `src/core/long_term_memory/`, `src/services/long_term_memory_service.py`,
  `src/modules/long_term_memory_module.py` — **zero changes**;
  Candidate A reads Long-Term Memory only indirectly, through
  `SemanticEngine`'s own existing public API. No archival,
  deduplication, or compaction logic is added here (Candidate D,
  Section 5, explicitly rejected for v1).
- `src/core/knowledge/`, `src/services/knowledge_service.py` — **zero
  changes**; reached only indirectly, same reasoning as above.
- `src/core/memory/`, `src/services/memory_service.py`,
  `src/modules/memory_module.py` — **zero changes**; Candidate A does
  not touch the raw namespaced `MemoryStore` at all (Section 6.4).
- `src/core/ai/conversation.py`, `src/core/ai/conversation_manager.py`
  — **zero changes**; Candidate C (Section 5), which would require
  modifying these, is explicitly rejected for v1.
- `src/core/ai/context_manager.py`, `src/core/ai/context_loader.py`,
  `src/core/ai/prompt.py`, `src/core/ai/prompt_builder.py`,
  `src/core/ai/prompt_manager.py`, `src/services/ai_service.py` —
  **zero changes**; Candidate A never wires into the automatic
  per-request pipeline (Section 6.4).
- `src/bootstrap.py` — **zero changes** (confirmed necessary and
  sufficient by Section 3.4's second finding: `CompressionEngine` is
  already constructed with a live `SemanticEngine` today).
- `config/config.yaml` — **zero changes** (Section 8).
- `src/core/command_router.py` — zero changes; the existing
  `compression` namespace and `CommandRouter.dispatch()` are used,
  never modified.
- `src/skills/reflection/`, `src/skills/prompt_optimizer/`,
  `src/skills/capability_registry/`, and every other existing skill
  — zero changes; no candidate considered here proposes modifying any
  existing skill.
- Every EP-001…EP-056 design/audit document and every other prior
  EP's source/test files, and `JARVIS_ROADMAP.md`/`BACKLOG.md`/
  `CHANGELOG.md`/`RELEASE_NOTES.md` (STEP 1 does not update
  documentation per this task's own instruction).

---

## 15. Compatibility considerations

Fully additive under Candidate A — no existing manager's method
signature, return type, or behavior changes; no existing config key's
meaning or default changes; no existing `CommandModule` action is
affected; `CompressionEngine`'s, `SemanticEngine`'s, and Long-Term
Memory's existing behavior for every other caller is unaffected,
since Candidate A only ever reads from them via already-existing,
unmodified public methods.

---

## 16. Implementation constraints

Bound by `AI_GENERATION_STANDARD.md` exactly as every prior EP was: no
architecture redesign, no invented API on `CompressionEngine`/
`SemanticEngine` ("Unknown API Policy"), one class one responsibility,
300-line-recommended/500-line-hard file-size limit (both files
modified are well under this limit today — Section 14's changes are
one method and one action handler, not a rewrite), type hints,
docstrings, no hardcoded credentials/paths.

---

## 17. Resource/operational limits

None beyond the already-existing `context_compression.enabled` gate
and `semantic.*`/`context_compression.*` limits (Section 7/8) —
Candidate A has no AI-provider cost surface, no filesystem write
surface, and no new rate-limit-worthy external call of any kind to
bound.

---

## 18. Acceptance criteria (for STEP 1)

- [x] Every roadmap/backlog/engineering-guide/prior-EP-cross-reference
  to EP-057/"Memory Optimization" was found and quoted verbatim
  (Section 2) — not summarized from memory.
- [x] The genuine absence of a functional specification is reported
  explicitly, not silently filled (Section 0/2).
- [x] The existing Memory & Context Manager (EP-013/023), Conversation
  Engine (EP-016), Context Loader (EP-018.5/018.6), Long-Term Memory
  (EP-025), Semantic Search (EP-026), and Context Compression (EP-027)
  were inspected in depth specifically to ground candidate
  interpretations in what already exists, not outside knowledge
  (Section 3).
- [x] The single strongest-looking piece of evidence
  (`compress_query()`'s zero-caller status) was explicitly weighed
  against three independently-derived alternatives rather than
  treated as an automatic conclusion (Section 5), per this task's
  explicit instruction.
- [x] At least the minimum necessary Owner Decision to proceed (D1, a
  definitional choice among repository-grounded candidates) is
  presented, with three further candidates explicitly considered and
  either recommended, deferred, or rejected with reasoning (Section
  5).
- [x] A complete, provisional architecture is presented for the
  *recommended* candidate only, explicitly marked contingent on D1's
  approval (Sections 6-17), and explicitly does not modify any
  existing subsystem's core files (Section 14's DO NOT MODIFY list).
- [x] File scope is narrow, explicit, and auditable — no directory-
  level authorization (Section 14).
- [x] No source, test, configuration, dependency, or Bootstrap file
  was created or modified.
- [x] STEP 2 has not begun.

---

## 19. Unresolved questions this document does not answer

Recorded explicitly, per the task's instruction not to silently guess:

- Whether the owner even agrees "Memory Optimization" should mean
  Candidate A at all — this is precisely Owner Decision D1, and this
  document's entire Sections 6-17 are void if the answer is anything
  else.
- Whether "Optimization" in the EP's title was ever intended to mean
  genuine footprint reduction/forgetting (Candidate B) or storage-
  layer compaction (Candidate D) rather than the narrower,
  retrieval-time "make what comes back from memory smaller and
  deduplicated" reading this document recommends (Candidate A) — no
  repository evidence resolves this either way; Sections 3.6/3.8
  already confirmed no metric/persistence/policy infrastructure
  exists today to build either alternative against even if the owner
  wants one of them.
- Whether a future EP-058 (Autonomous Planning) will expect
  `compression query`'s output in a specific, machine-readable
  format, or will want it wired automatically into planning's own
  context assembly — no such requirement exists anywhere in the
  repository today (mirroring EP-055's and EP-056's own, identically-
  worded open questions about their own successors), so this document
  assumes on-demand-only invocation and the existing
  `CompressionResult` shape are sufficient for v1, flagged as
  revisitable.
- Whether extending `ConversationManager`'s dead `truncate_strategy`
  key (Candidate C) is a direction the owner wants pursued at all,
  now or later, independently of whichever candidate D1 selects —
  recorded as rejected for v1 but not foreclosed permanently.
- Whether `compression` is the right namespace for the new action, or
  whether a new `memory`-branded namespace (or an addition to `ltm`)
  would read more naturally given the EP's own title — recorded as
  part of Owner Decision D4 (Section 6.1).

---

## 20. Owner Decisions

None of the decisions below is yet approved. Sections 6-17's
provisional architecture is **not** authorized for STEP 2 until D1 is
approved (and D2-D4, where applicable, are resolved).

### D1 — What does "Memory Optimization" concretely mean for v1? (primary, definitional decision)

**Question:** Which of Section 5's candidate interpretations (or an
owner-supplied alternative not considered here) should EP-057 v1
actually build?
**Options:** (a) Candidate A — expose `CompressionEngine.
compress_query()`/`compress_semantic_results()` (EP-027) as a new
`compression query` on-demand action, giving Long-Term Memory/
Knowledge Base retrieval a deduplicated, size-bounded output
(recommended); (b) Candidate B — usage/access-frequency-based
adaptive memory pruning (not recommended — requires inventing a
metric/persistence/policy scheme from nothing, Section 3.8); (c)
Candidate C — implement a real, second `conversation.truncate_strategy`
value, closing the confirmed dead configuration key (Section 3.2),
requiring modification of EP-016's `Conversation`/`ConversationManager`
(viable fallback if the owner specifically wants EP-057 to close a
*confirmed dead config key* rather than expose an *unused-but-live*
capability); (d) Candidate D — automatic archival/deduplication
policy inside Long-Term Memory itself (not recommended for v1 —
requires inventing a policy from nothing and modifying EP-025's own
core files, Section 3.6); (e) an owner-supplied alternative, in which
case this entire document would need to be revised before STEP 2.
**Recommended option:** (a).
**Technical reasoning:** (a) is the only candidate grounded in a
component that is already fully implemented, already tested, and
already wired end-to-end in a running Bootstrap (Section 3.4) — the
smallest implementation gap, zero Bootstrap change, and zero
configuration change of any candidate considered. (b) and (d) both
require inventing a policy/metric this document has no repository
evidence to derive. (c) is real and grounded (a confirmed dead config
key, Section 3.2) but requires modifying an already-complete,
already-audited subsystem (EP-016) rather than being purely additive.
**Security impact:** (a) introduces no new gate (reuses
`context_compression.enabled`) and makes no AI-provider call — the
smallest security surface of any candidate considered; (b) would need
its own, new persistence/gating design; (c) has a similarly small
surface to (a) but touches a second subsystem's core files; (d) is
unscoped until its own policy is designed.
**Compatibility impact:** (a) is fully additive; (b) and (d) are
unscoped; (c) modifies `Conversation`/`ConversationManager`.
**What changes in STEP 2:** (a) → build exactly Section 14's file
scope. (b) → this document would need a full revision specifically
designing a usage-metric/persistence/pruning scheme before STEP 2
could begin. (c) → Section 6/14 would need to be rewritten to scope
`Conversation._truncate_locked()`'s new strategy and its own test
surface. (d) → this document would need a full revision scoping a
Long-Term Memory archival/deduplication policy and its own,
independent design before STEP 2 could begin.

### D2 — Should `compression query` expose `top_k`/`threshold` as CLI-overridable arguments, or rely on `semantic.*` defaults only?

**Question:** `compress_query()` already accepts optional `top_k`/
`threshold` overrides (Section 6.3). Should v1's `compression query`
CLI action expose them as optional trailing arguments (e.g.
`compression query "<text>" [top_k] [threshold]`), or should v1 rely
solely on the already-configured `semantic.top_k`/
`semantic.similarity_threshold` defaults, with no per-call override?
**Options:** (a) defaults only, no CLI override (simplest, smallest
argument-parsing surface); (b) expose both as optional positional or
flag-style arguments.
**Recommended option:** (a) — `semantic search` itself (the
established naming precedent, Section 6.1) does not expose per-call
`top_k`/`threshold` overrides either (`config/config.yaml` line 842's
own comment: "Both can be overridden per call via
`SemanticEngine.search()`, but are not exposed as CLI arguments in
this EP") — matching that precedent keeps `compression query`
consistent with the one CLI action it is most directly modeled on.
**Security impact:** none either way.
**Compatibility impact:** none either way — purely a v1 argument-
surface decision, extendable later without breaking change.
**What changes in STEP 2:** (a) → `_query()`'s handler takes exactly
one argument (the query text, space-joined, mirroring `_compress()`).
(b) → `_query()` additionally parses and validates up to two more,
optional, positional arguments.

### D3 — Is `compression query`'s information disclosure acceptable given the existing `semantic search`/`ltm list`/`ltm info` precedent?

**Question:** Section 7 argues `compression query` discloses nothing
`semantic search`/`ltm list`/`ltm info` do not already disclose today
(in a less-processed form). Does the owner agree, or is there a
reason (not evidenced in the repository today) to treat compressed/
deduplicated aggregate disclosure differently from per-record
disclosure?
**Options:** (a) accept Section 7's reasoning — no additional gate
beyond `context_compression.enabled` (as proposed); (b) require a
second, independent gate anyway (mirroring EP-055's own Owner
Decision D3 and EP-056's own Owner Decision D3 pattern, applied out
of caution rather than a repository-evidenced need).
**Recommended option:** (a).
**Security impact:** (a) is a single point of control, consistent
with the actual disclosure-equivalence finding; (b) adds a flag with
no corresponding new risk this document could identify.
**Compatibility impact:** none either way — new, independent action
regardless.
**What changes in STEP 2:** (a) → Section 8's "no new configuration"
claim stands unchanged. (b) → an additional
`context_compression.allow_query`-style key (or equivalent), checked
alongside `context_compression.enabled`.

### D4 — Command namespace and action name (Section 6.1)

**Question:** Should the new capability live as `compression query`
on the existing `compression` namespace (as proposed), as a new
action on the existing `ltm` namespace instead, or under a new,
EP-057-specific namespace (e.g. `memory-optimize`)?
**Options:** (a) `compression query` (as proposed); (b) a new action
on `ltm` (e.g. `ltm query <text>`), requiring `LongTermMemoryModule`
to take a new dependency on `CompressionService`; (c) a new,
dedicated namespace.
**Recommended option:** (a) — no existing `CommandRouter` namespace
collision, no new cross-module dependency required (Section 6.1), and
the closest naming/behavioral fit to both `compression compress`
(same namespace) and `semantic search` (same query-shaped verb
convention).
**Security impact:** none either way.
**Compatibility impact:** (a) is the smallest diff; (b) requires a
new constructor dependency on an already-complete module; (c) is
unscoped until the new namespace itself is designed.
**What changes in STEP 2:** (a) → build exactly Section 6.3's table
under `compression`. (b) → `LongTermMemoryModule.__init__` gains a
`compression_service` parameter, and `src/bootstrap.py`'s
construction-ordering (Section 3.4) would need to guarantee
`compression_service` exists before `LongTermMemoryModule` is
constructed — a Bootstrap change this document's recommended option
(a) avoids entirely. (c) → this document would need a full revision
scoping the new namespace, its own `CommandModule`, and its own
Bootstrap wiring.

---

## Owner Approval Checklist

**Owner-approved on the date this section was updated, exactly as
recommended, with no modification to any option below.**

- [x] **D1** — What does "Memory Optimization" concretely mean for
  v1? **APPROVED: Candidate A** — expose the existing EP-027
  `CompressionEngine.compress_query()`/`compress_semantic_results()`
  through `compression query "<text>"`.
- [x] **D2** — Expose `top_k`/`threshold` as CLI arguments?
  **APPROVED: no** — rely on the existing `semantic.*` configuration
  defaults.
- [x] **D3** — Additional information-disclosure gate beyond
  `context_compression.enabled`? **APPROVED: no** — none required.
- [x] **D4** — Command namespace and action name. **APPROVED: extend
  the existing `compression` namespace with `compression query`.**

**STEP 3 architecture audit
(`docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md`) found zero
blocking findings — no D5-equivalent Owner Decision was raised or
required to proceed to STEP 4**, unlike EP-055's/EP-056's own STEP 3
audits. Three non-blocking findings (a stale `src/bootstrap.py`
comment; a test-coverage/naming gap around the
`context_compression.enabled: false` gate; and this document's own
absence from the repository tree) were identified and closed during
STEP 4 finalization without altering D1-D4 or any part of Candidate
A's approved scope (Sections 6-17 above) — see
`EP057_ARCHITECTURE_AUDIT.md` Section 19 for the full remediation
record.
