# Phase C — AI Content Platform (Parent Phase, planning only)
## EP-082 — Text Generation Provider Integration

STEP 1: Architecture Discovery & Design

Status: STEP 1 COMPLETE — APPROVED, READY FOR STEP 2

---

## 0. How this scope was derived

`docs/architecture/JARVIS_ROADMAP.md` lists EP-082 only inside
"Phase C — AI Content Platform (planning only)," as part of the
range EP-082–EP-087, and points to `docs/BACKLOG.md` for detail.
`docs/BACKLOG.md`'s "AI Content Platform (EP-082–EP-087)" section
gives the one-line scope actually in force:

> **EP-082 — Text Generation Provider Integration** (MEDIUM)

EP-087 ("Content Production Pipeline") explicitly states the whole
phase is meant to combine text/image/audio/video/presentation
generation "through the EP-069 provider abstraction" — i.e. EP-082 is
scoped as an *integration* of text generation into the existing
AI-provider architecture (EP-014/015/069), not a new, parallel AI
subsystem.

This document's initial STEP 1 draft raised three architectural
questions that required Owner approval before implementation could
proceed safely. **All three have now been decided by the Owner**
(Section 20 records the decisions); this revision resolves every part
of the design against those decisions. No ambiguity or pending
choice remains — this document now describes one approved
architecture.

---

## 1. Title

EP-082 — Text Generation Provider Integration

## 2. Status

STEP 1 complete and Owner-approved. STEP 2 (Implementation & Testing)
may begin. STEP 3 (Architecture Audit) and STEP 4 (Documentation
Synchronization) have not started. No production code, tests, or
configuration have been modified by this document.

---

## 3. What exactly is this EP, and why does it exist?

Phase C (AI Content Platform) needs Jarvis to be able to produce
text content on request (articles, summaries, marketing copy,
captions, social posts, presentation body text, etc.) as a
first-class, reusable capability — not just as a conversational
chat reply. EP-082 is the foundational slice of that phase: it wires
**text generation** into the existing, already-built AI provider
abstraction (`AIProvider`, `ProviderRegistry`, `ProviderManager` —
EP-014/015, extended by EP-069.1/.2/.3's fallback and cost-aware
selection) so that later EPs in this phase (EP-083 image, EP-084
audio/speech, EP-085 video, EP-086 presentations, EP-087's combined
pipeline) all have one non-duplicated way to ask for generated text,
instead of each building its own provider-calling code.

## 4. What problem does it solve?

Today, "asking a provider for text" exists in exactly two forms in
this repository, and neither is a fit for standalone content
generation on its own:

1. **`AIService.ask()`** (`src/services/ai_service.py`) — the
   EP-018 conversational pipeline (User → Conversation Engine →
   Context Engine → Prompt Engine → ProviderManager → Provider). It
   unconditionally records the request/reply into the active
   `Conversation` (EP-016) when `conversation.enabled` is true, and
   pulls project/working-directory context via the Context Engine.
   A content-generation request (e.g. "write a 500-word product
   description") is not a conversational turn and must not be
   recorded as one, and normally has no need for project context.
2. **Direct `ProviderManager.get_current()` +
   `AIProvider.ask()`** — the pattern `ReflectionModule` (EP-054)
   and `PromptOptimizerModule` (EP-055) use specifically *because*
   they need to bypass `AIService`'s conversation side effects. This
   avoids conversation pollution but also bypasses EP-069.1/.2/.3's
   fallback and cost-aware provider selection entirely, since that
   logic today lives only inside `AIService.ask()`'s request loop
   (`src/services/ai_service.py`, lines ~549-604).

**Resolved (Section 20, Decision 1):** the fallback/retry logic is
extracted into a new shared component, `ProviderRequestExecutor`, so
both `AIService` and the new `TextGenerationService` get
non-duplicated fallback execution without either owning a second
implementation of it.

## 5. What already exists (Existing Functionality Analysis)

| Existing component | Location | Classification | Reason |
|---|---|---|---|
| `AIProvider` (ABC), `ProviderStatus`, `ProviderHealth`, `ProviderResponse`, `ProviderError` hierarchy | `src/core/ai/provider.py` | **REUSE, ADDITIVELY EXTEND** | Exactly the contract EP-082 needs a text response from; extended only with the two new optional `ask()` parameters (Section 12). |
| `ProviderRegistry`, `ProviderFactory` | `src/core/ai/provider_registry.py`, `provider_factory.py` | **REUSE** | Catalog/construction is provider-identity concerns, unrelated to *how* a caller requests text; unchanged. |
| `ProviderManager` (`get_current()`, `list_fallback_candidates()`, cost-aware ordering) | `src/core/ai/provider_manager.py` | **REUSE, UNCHANGED** | Provider selection, candidate ordering, and cost-aware ordering remain exactly ProviderManager's responsibility. Per Owner Decision 1, the retry *execution* loop is explicitly NOT added here — it moves to the new `ProviderRequestExecutor` (Section 11.2), keeping `ProviderManager` a pure selection/registry component. |
| `ClaudeProvider`, `GeminiProvider` | `src/core/ai/claude_provider.py`, `providers/gemini_provider.py` | **ADDITIVELY EXTEND** | Both already implement real `ask()`; extended only to honor the new optional `temperature`/`system_prompt` parameters when supplied (Section 12). No new provider implementation. |
| `AIService.ask()`'s fallback retry loop | `src/services/ai_service.py:468-613` | **EXTRACT, DO NOT DUPLICATE** | Moves into `ProviderRequestExecutor` (Section 11.2). `AIService.ask()` calls the extracted executor instead of owning the loop; its own public signature, `AskResult` contract, and all conversation/context/prompt behavior are unchanged (Section 8, 19). |
| `ReflectionModule` / `PromptOptimizerModule` direct-provider pattern | `src/skills/reflection/skill.py`, `src/skills/prompt_optimizer/skill.py` | **PRECEDENT ONLY, NOT MODIFIED** | Establishes that bypassing `AIService` for non-conversational AI use is an accepted, existing pattern. Neither module is modified by EP-082 and neither gains fallback — they are unaffected by this EP. |
| `CommandModule` Protocol / `CommandRouter` | `src/core/command_router.py` | **NOT USED (DEFERRED)** | Per Owner Decision 2, EP-082 adds no CLI namespace. `CommandRouter` is not touched. |
| `src/skills/presentation/`, other skill stub files | `src/skills/presentation/skill.py`, etc. | **NO CHANGE** | Empty (0-byte) placeholders for later phase-C EPs (e.g. EP-086). Out of scope for EP-082. |
| `config/config.yaml` `ai:` / `providers:` sections | `config/config.yaml` | **UNCHANGED; NEW ADDITIVE SECTION ADDED** | Per Owner Decision 3, a new top-level `content_generation:` section is added; `ai:` and `providers:` semantics are not altered. |

---

## 6. Approved architecture summary

Per Owner Decision 1 (Section 20), the approved shape is:

```text
AIService  ---\
               \
                --> ProviderRequestExecutor --> ProviderManager --> AIProvider
               /
TextGenerationService  ---/
```

Responsibilities are split as follows, with no overlap:

- **`ProviderManager`** (unchanged responsibilities)
  - provider registry / current-provider access
  - fallback candidate ordering (EP-069.2)
  - cost-aware ordering/selection (EP-069.3)
  - provider registration/removal/lookup

- **`ProviderRequestExecutor`** (new, shared, EP-082)
  - executes a single provider request end-to-end
  - applies the existing EP-069.1 fallback/retry semantics exactly
    as `AIService.ask()` implements them today (Section 15)
  - excludes already-attempted providers on each retry
  - stops immediately on a non-fallback-eligible error
  - returns/propagates a single, consistent outcome type to its
    caller (Section 15)
  - has no knowledge of Conversation, Context, or Prompt Engine —
    it operates purely at the provider level

- **`AIService`** (unchanged public behavior)
  - owns conversation/context/prompt orchestration exactly as before
  - `ask()` now calls `ProviderRequestExecutor` instead of running
    its own inline retry loop; its own signature, `AskResult`
    contract, and all observable behavior are unchanged (Section 8)

- **`TextGenerationService`** (new, EP-082's actual deliverable)
  - standalone content-generation entry point
  - no conversation, no context, no persistence (Section 9)
  - calls the same `ProviderRequestExecutor` as `AIService`

This directly satisfies Rule 3/Rule 4 ("never introduce a second
implementation of existing functionality" / "never duplicate
infrastructure or business logic"): there is exactly one fallback/
retry implementation in the repository, used by two callers.

---

## 7. Scope Definition

### IN SCOPE
- New `ProviderRequestExecutor` (Section 11.2), extracted from
  `AIService.ask()`, behavior-preserving.
- `AIService.ask()` updated internally to call the extracted
  executor; public contract unchanged (Section 8, 19).
- New `TextGenerationService` (Section 11.1): standalone text
  generation using `ProviderRequestExecutor`.
- Additive `AIProvider.ask()` extension: optional `temperature` and
  `system_prompt` keyword parameters (Section 12).
- Additive `content_generation:` configuration namespace
  (Section 13), containing only what EP-082 itself needs.
- New `tests/EP082/` test suite, following existing repository
  convention (`tests/EP069`, `tests/EP069_2`, `tests/EP069_3`).
- Dependency wiring for `TextGenerationService` and
  `ProviderRequestExecutor` in `src/bootstrap.py`.

### OUT OF SCOPE
- Image, audio, video, or presentation generation (EP-083–EP-086).
- The "Content Production Pipeline" combining multiple modalities
  (EP-087) — EP-082 is a dependency of it, not a slice of it.
- Any new AI provider implementation (e.g. OpenAI, DeepSeek).
- Any new LLM function/tool-calling capability (unrelated; remains
  EP-069's own deferred concern per `EP069_DESIGN.md` Section 0.1).
- Streaming responses — not present anywhere in the current
  `AIProvider` contract; not introduced here.
- **CLI/CommandRouter surface — explicitly deferred (Section 20,
  Decision 2).**
- Any configuration structure for EP-083–EP-086's future needs
  (Section 13 defines only what EP-082 itself requires).
- Rewriting or re-issuing `EP069_DESIGN.md` / `EP069_2_DESIGN.md` /
  `EP069_3_DESIGN.md`. EP-082 preserves EP-069's behavior exactly
  (Section 15); any cross-referencing documentation update these
  historical documents might warrant is a STEP 4 (Documentation
  Synchronization) concern for EP-082 itself, not a rewrite of
  EP-069's own historical record.

### DEFERRED
- Content-specific prompt templates/style presets (blog post,
  caption, product description, etc.) — candidate for EP-087 or a
  dedicated future sub-package once real usage patterns exist.
- Persisting generated content (drafts, revisions, versioning) — no
  persistence requirement is stated in the backlog line, and
  `TextGenerationService` explicitly does not persist output
  (Section 9).
- CLI/user-facing content-generation workflow — deferred to EP-087
  or another explicitly scoped future EP (Section 20, Decision 2).

### FUTURE INTEGRATION
- EP-083–EP-086 are expected to follow the same pattern established
  here: use `ProviderRequestExecutor` for retry/fallback rather than
  each re-implementing it.
- EP-087 will compose `TextGenerationService` alongside EP-083–086's
  equivalents.

---

## 8. Architectural context — existing layers involved

Only the layers actually touched:

- **Core infrastructure / Domain layer** — `src/core/ai/` (provider
  contract, new `ProviderRequestExecutor`) — extended.
- **Service layer** — `src/services/ai_service.py` (internal-only
  change, Section 19) and new `src/services/text_generation_service.py`.
- **Execution/CLI layer** — not touched (Section 20, Decision 2).

No Planning, Workflow, Memory/Knowledge, Automation, or external
Integration layer is relevant to this EP; none are touched.

---

## 9. Non-conversational semantics (`TextGenerationService`)

`TextGenerationService` is a standalone capability over the existing
provider infrastructure. It explicitly:

**MUST NOT:**
- create or update conversation history;
- call `ConversationManager` in any way;
- implicitly load project or working-directory context;
- call `ContextManager`;
- create memory entries via `MemoryService`/`MemoryManager`;
- persist generated content in any form (no drafts, no versioning);
- depend on, wrap, or call through `AIService.ask()`'s conversational
  pipeline.

**MUST:**
- call `ProviderRequestExecutor` directly for provider execution;
- return a plain, self-contained result (Section 14) with no
  conversation-, context-, or persistence-related fields.

---

## 10. Dependency analysis

**Upstream dependencies (must already exist):**
- `AIProvider`, `ProviderRegistry`, `ProviderManager`,
  `ProviderFactory` (EP-014) — REQUIRED, already built.
- `ClaudeProvider` / `GeminiProvider` real `ask()` (EP-015/015.1) —
  REQUIRED, already built.
- EP-069.1 fallback, EP-069.2 fallback ordering, EP-069.3 cost-aware
  selection — REQUIRED; their exact semantics are preserved
  unchanged inside the extracted `ProviderRequestExecutor`
  (Section 15).

**Downstream consumers (expected to depend on EP-082):**
- EP-087 (Content Production Pipeline) — REQUIRED consumer.
- EP-083–EP-086 — expected to follow the same architectural pattern
  (Section 7, Future Integration).

**Runtime dependencies:** whichever provider(s) are enabled in
`config/config.yaml` `providers:` — no new runtime service needed.

**Architectural dependencies:** the `ProviderError` hierarchy
(fallback eligibility classification) is used exactly as EP-069.1
defined it; not modified.

---

## 11. Component design

### 11.1 `TextGenerationService`

Location: `src/services/text_generation_service.py` (new file).

Responsibilities:
- Accept a content-generation request: prompt/instruction text, and
  optional per-request `temperature`/`system_prompt` overrides
  (Section 12).
- Delegate execution to `ProviderRequestExecutor`, which resolves
  the provider via `ProviderManager` (current provider, with
  fallback if enabled) exactly as `AIService.ask()` does today.
- Return a `TextGenerationResult` (Section 14) with no conversation,
  context, or persistence coupling (Section 9).
- Perform no prompt templating and no content-type-specific logic
  (blog/caption/etc.) — DEFERRED (Section 7).

### 11.2 `ProviderRequestExecutor`

Location: `src/core/ai/provider_request_executor.py` (new file, same
layer/package as `provider.py`/`provider_manager.py`/
`provider_registry.py`, consistent with this project's existing
one-file-per-component convention in `src/core/ai/`).

Responsibilities:
- Given a rendered prompt string (and optional `temperature`/
  `system_prompt`), attempt the currently selected provider via
  `ProviderManager.get_current()`.
- On a fallback-eligible `ProviderError`
  (`ProviderUnavailableError`, `ProviderNetworkError`,
  `ProviderTimeoutError`, `ProviderRateLimitError` — unchanged from
  EP-069.1), retrieve `ProviderManager.list_fallback_candidates()`
  (excluding every provider already attempted) and retry, in the
  order `ProviderManager` returns (unchanged EP-069.2/.3 ordering).
- On a non-fallback-eligible error (`ProviderConfigurationError`,
  `ProviderAuthenticationError`, base `ProviderError`), stop
  immediately — no retry.
- Stop when every eligible candidate has been attempted, returning a
  deterministic failure outcome (Section 15).
- Has no dependency on `Conversation`, `ContextManager`, or
  `PromptManager` — it accepts an already-final prompt string, the
  same contract `AIProvider.ask()` itself uses.

`AIService.ask()` is updated to call `ProviderRequestExecutor`
instead of running its own inline loop; it continues to own
building the conversation/context/prompt pipeline exactly as before,
and passes the final rendered prompt to the executor. Its own method
signature and `AskResult` return type do not change (Section 19).

---

## 12. Provider contract extension

`AIProvider.ask()` gains two new **optional** keyword parameters:

```python
def ask(
    self,
    prompt: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
    system_prompt: str | None = None,
) -> ProviderResponse:
```

**`temperature=None`** means: preserve this provider's existing
configured/default temperature behavior exactly as today (read from
`providers.<name>.temperature`, per `ClaudeProvider`/`GeminiProvider`'s
constructor). It must never be interpreted as "force zero" or any
other implicit value — `None` means "no override; use the existing
default path unchanged."

**`system_prompt=None`** means: no per-request system-prompt
override is supplied; the provider's existing prompt-handling
behavior (as `AIService`'s Prompt Engine already renders it into
`prompt`) is unchanged.

**Backward compatibility:** every existing caller (`AIService`,
`ReflectionModule`, `PromptOptimizerModule`, and all current tests)
calls `ask()` with zero or one positional/keyword argument
(`prompt`, optionally `max_tokens`) and is therefore source- and
behavior-compatible with no code change, since both new parameters
default to `None` and `None` is defined above to mean "unchanged
behavior."

`ClaudeProvider` and `GeminiProvider` are each extended (not
replaced) to translate a non-`None` `temperature` into their
respective API call's temperature field, and a non-`None`
`system_prompt` into their respective API's system-prompt field,
when supplied. No new provider, provider abstraction, provider
registry, or provider manager is introduced (Owner Decision,
Section 10 of the Owner's directive).

### 12.1 Temperature validation

Single architectural rule, enforced once, at the contract boundary
(`AIProvider.ask()`'s shared entry semantics — validated by each
concrete provider's `ask()` before translating to its own API call,
since `AIProvider` is an ABC with no shared method body to validate
inside; both `ClaudeProvider.ask()` and `GeminiProvider.ask()` apply
the identical rule):

- **Accepted type:** `float` (an `int` such as `0` or `1` is
  accepted and treated as its float equivalent, consistent with
  Python's normal numeric handling; not explicitly rejected).
- **`None` is allowed** and means "no override" (Section 12).
- **Valid numeric range:** `0.0` to `1.0` inclusive — matching the
  range already implied by both providers' existing
  `providers.<name>.temperature` configuration values (used as the
  provider's own default when the per-request override is `None`).
- **Invalid value behavior:** a `temperature` outside `0.0`–`1.0`
  (when not `None`) raises `ProviderConfigurationError` — the
  existing, already-defined exception this project uses for
  invalid/unusable configuration (Section 15's error table extends
  naturally to this case since it is a caller-configuration problem,
  not a network/runtime one). No new exception class or validation
  framework is introduced.

---

## 13. Configuration

New, additive, top-level section in `config/config.yaml`:

```yaml
content_generation:
  # EP-082 Text Generation Provider Integration. Additive namespace;
  # does not alter 'ai:' or 'providers:' semantics. Governs standalone
  # (non-conversational) text-generation requests only.
  enabled: false
  # Default temperature used when a TextGenerationService caller does
  # not supply a per-request override (None). Must be within the
  # 0.0-1.0 range defined in Section 12.1.
  default_temperature: 0.7
  # Whether TextGenerationService requests use the same
  # fallback/cost-aware provider selection AIService.ask() uses.
  # Independent of, and defaults to matching, 'ai.fallback_enabled'.
  fallback_enabled: false
```

Only the settings EP-082 itself requires are defined here; no
speculative structure for EP-083–EP-086 is added (per the Owner's
explicit instruction). `ai:` and `providers:` are not modified.

---

## 14. `TextGenerationResult` contract

Minimal successful result:

```python
@dataclass(frozen=True)
class TextGenerationResult:
    success: bool
    text: str
    provider_name: str
    model_name: str
    error: str
```

- `text`, `provider_name`, `model_name` are populated on success
  (`provider_name`/`model_name` mirror `AskResult`'s existing
  `provider`/`model` fields for consistency with the established
  convention in `src/services/ai_service.py`).
- No conversation-related metadata (no turn IDs, no history
  references).
- No persistence/versioning metadata (no draft IDs, no timestamps
  beyond what logging already captures).
- No speculative content-type fields (no "content_type", "word_count",
  etc.) — these are DEFERRED (Section 7) until a concrete consumer
  needs them.

**Failure semantics — one consistent convention, matching
`AIService.ask()`'s existing pattern exactly:**

`TextGenerationService` never raises a `ProviderError` to its
caller. Every failure — no provider selected, provider disabled,
non-fallback-eligible error, or all fallback candidates exhausted —
is reported as `TextGenerationResult(success=False, text="",
provider_name=..., model_name="", error=<message>)`, mirroring how
`AIService.ask()` already returns a failed `AskResult` rather than
letting `ProviderError` propagate to its own callers. This is a
direct reuse of the existing service-layer convention, not a new
error-handling policy, and avoids the inconsistency of some failures
being raised and others returned.

`ProviderRequestExecutor` itself (the shared, lower-level component)
propagates the same outcome shape both its callers need: it returns
a result object indicating success/failure plus enough detail
(final provider name, response or error) for `AIService` to build
`AskResult` and `TextGenerationService` to build
`TextGenerationResult` from the same underlying execution outcome,
so neither caller needs to catch a raised `ProviderError` from the
executor for the fallback-exhausted or non-eligible-failure cases.

---

## 15. Fallback semantics (preserved exactly from EP-069)

`ProviderRequestExecutor` implements the following, unchanged from
`AIService.ask()`'s current behavior:

1. Attempt the current/selected provider (`ProviderManager
   .get_current()`).
2. Catch only fallback-eligible `ProviderError` subclasses:
   `ProviderUnavailableError`, `ProviderNetworkError`,
   `ProviderTimeoutError`, `ProviderRateLimitError`.
3. On a fallback-eligible failure, and only when fallback is enabled
   for the calling context, obtain remaining candidates via
   `ProviderManager.list_fallback_candidates(exclude=attempted)`.
4. Candidate ordering is whatever `ProviderManager` currently
   returns (alphabetical by default, or EP-069.2 configured order,
   or EP-069.3 cost-aware order) — unchanged, not re-implemented.
5. Retry the next candidate; repeat from step 2.
6. On a non-fallback-eligible error
   (`ProviderConfigurationError`, `ProviderAuthenticationError`, base
   `ProviderError`), stop immediately — no retry, regardless of
   fallback being enabled.
7. When every eligible candidate has been attempted, return a
   deterministic failure outcome aggregating each attempt (provider
   name + exception class only, never raw exception text derived
   from user content — preserving the existing log-redaction
   precedent, `EP069_DESIGN.md` Section 9/11).

No new fallback-eligible exception is introduced; the set is not
broadened. `AIService.ask()`'s "fallback within a single request
never changes the 'current' provider for the next request" rule
(EP-069.1 Owner Decision D1) is preserved unchanged, since
`ProviderManager.get_current()`/`set_current()` are not touched by
the executor.

`TextGenerationService` requests use the same executor and therefore
the same semantics; whether fallback is attempted for a given
`TextGenerationService` call is governed by
`content_generation.fallback_enabled` (Section 13), independently
configurable from `ai.fallback_enabled`, since content-generation
requests are a distinct calling context from chat.

---

## 16. Security

- **Secrets:** no new credential type — reuses whichever provider
  API keys are already configured under `providers.*`. No new
  secret is introduced or logged.
- **Untrusted input:** the prompt/instruction text passed to
  `TextGenerationService` is user-authored content, the same trust
  level as any existing `AIService.ask()` prompt.
- **Logging:** failure logging follows the same redaction precedent
  as `AIService.ask()` (provider name + exception class only) —
  applied identically inside `ProviderRequestExecutor` since it is
  now the single place this logging happens for both callers.
- No new network or filesystem access beyond calling an
  already-configured, already-network-capable provider.

---

## 17. Error handling

| Failure | Detection | System behavior | Result | Logging |
|---|---|---|---|---|
| No provider currently selected | `ProviderManager.get_current()` is `None` | Fail immediately, no executor call | `TextGenerationResult(success=False, error="No AI provider selected")` (mirrors `AIService`'s existing `_NO_PROVIDER_SELECTED`) | Info-level, no exception |
| `content_generation` disabled | `content_generation.enabled` is `false` | Fail immediately | `TextGenerationResult(success=False, error="Text generation is disabled...")` | Info-level |
| Invalid `temperature` (outside 0.0-1.0) | Provider's `ask()` validation (Section 12.1) | Raise `ProviderConfigurationError` before any network call | Caught by `TextGenerationService`/`ProviderRequestExecutor`, returned as a failed result (Section 14) | Provider name + exception class only |
| Fallback-eligible `ProviderError` | `isinstance(exc, _FALLBACK_ELIGIBLE_ERRORS)` | Retry next candidate (Section 15) | Success result once a candidate succeeds, else exhausted-failure result | Provider name + exception class only |
| Non-eligible `ProviderError` (config/auth) | Existing EP-069.1 classification | Fail immediately, no retry | Failed result with provider's error message | Provider name + exception class only |
| All eligible providers exhausted | `list_fallback_candidates()` empty | Fail with aggregated summary | Failed result: "All providers failed. ..." (mirrors `AIService.ask()`'s existing message) | Aggregated provider/exception names only |

No new failure classes are introduced; the existing `ProviderError`
hierarchy is reused exactly as EP-069.1 defined it.

---

## 18. Testing strategy (for STEP 2 — not performed here)

Following existing repository convention (`tests/EP069`,
`tests/EP069_2`, `tests/EP069_3`), STEP 2 creates `tests/EP082/`
covering:

- Unit tests for `ProviderRequestExecutor` with fake/stub
  `AIProvider` instances (no real network calls), verifying it
  reproduces `AIService.ask()`'s existing fallback behavior
  identically.
- **Regression tests:** `AIService.ask()`'s full existing test suite
  must still pass unmodified after the extraction — this is a
  required, not optional, part of STEP 2's acceptance.
- Unit tests for `TextGenerationService`: success path, disabled
  config, no-provider-selected, fallback success, fallback
  exhaustion, non-eligible immediate failure.
- Additive-parameter tests on `ClaudeProvider`/`GeminiProvider`:
  `temperature`/`system_prompt` omitted (byte-for-byte unchanged
  behavior vs. pre-EP-082) vs. provided (override applied); invalid
  `temperature` raises `ProviderConfigurationError` (Section 12.1,
  17).

---

## 19. `AIService` backward compatibility (mandatory)

The extraction of the retry loop into `ProviderRequestExecutor` MUST
preserve, unchanged:

- `AIService.ask()`'s public method signature.
- The `AskResult` return type and its field semantics.
- Conversation behavior (`_begin_turn`/`_complete_turn`, recording
  exactly as today).
- Context behavior (`ContextManager.create()` usage, unchanged).
- Prompt Engine behavior (`PromptManager.build()` usage, unchanged).
- Fallback eligibility rules (Section 15) — identical set of
  exceptions.
- Fallback candidate ordering — identical, via unchanged
  `ProviderManager` calls.
- All user-visible behavior and error messages.

Only the internal location of the retry loop changes: `AIService
.ask()` now calls `ProviderRequestExecutor` instead of running the
loop inline. This is implementation-internal refactoring of an
already-shipped method, not a contract change, and STEP 2's
regression test suite (Section 18) is the acceptance gate for this
requirement.

---

## 20. Owner Decisions — RESOLVED

```text
DECISION 1 — Shared fallback/retry execution
APPROVED: Extract AIService.ask()'s retry loop into a new, shared
ProviderRequestExecutor (Section 11.2), used by both AIService and
TextGenerationService. ProviderManager's responsibilities are
unchanged (provider selection/ordering only); it does not gain the
retry loop. AIService.ask()'s public behavior is fully preserved
(Section 19).
```

```text
DECISION 2 — CLI surface
DEFERRED (not added by EP-082).
Reason: EP-082 is provider integration infrastructure; concrete
content-production UX belongs to later EPs, especially EP-087.
CommandRouter is not touched by this EP.
```

```text
DECISION 3 — Configuration namespace
APPROVED: content_generation: (top-level, additive; Section 13).
ai: and providers: semantics are not altered. Only the settings
EP-082 itself requires are defined; no structure for EP-083-086 is
speculated.
```

No further Owner Decisions are outstanding. Any remaining
implementation-level naming choices (Section 21, Open Questions) do
not affect architecture and may be resolved during STEP 2.

---

## 21. Parallel development safety

Shared files this EP touches that other EPs may also touch:

- `src/bootstrap.py` — every skill/service-adding EP modifies this
  file to wire its component (EP-054, EP-055, EP-056 each did this).
  If EP-083–EP-086 (Phase C siblings) are implemented around the
  same time, both this EP's and their edits will land in the same
  file — a normal merge-coordination point, not a design conflict:
  each EP's addition is independent and additive within the file.
- `config/config.yaml` — same shared-file characteristic; EP-082's
  `content_generation:` key and any sibling EP's own top-level key
  are independent and do not conflict structurally.
- `src/core/ai/provider.py`, `claude_provider.py`, `gemini_provider.py`
  — touched by this EP's additive extension (Section 12); no other
  currently-planned EP is known to touch these files concurrently.

```text
PARALLEL DEVELOPMENT AWARENESS
Potential overlap: src/bootstrap.py, config/config.yaml
Affected files: src/bootstrap.py, config/config.yaml
Reason: Every new skill/service EP registers itself in both files;
concurrent edits from sibling Phase C EPs are structurally additive,
not conflicting, but should be reviewed together at merge time.
```

EP-082 does not modify any other EP's already-implemented behavior
except the single, now-approved extraction described in Section 19.

---

## 22. Risks

- The `AIService.ask()` extraction touches a shipped, documented
  component; STEP 2's regression suite (Section 18) is the mitigation
  and is mandatory, not optional.
- Additive `temperature`/`system_prompt` parameters touch two
  provider implementations; STEP 2 must verify neither provider's
  existing `ask()` tests are affected when the new parameters are
  omitted.
- `content_generation.fallback_enabled` being independently
  configurable from `ai.fallback_enabled` (Section 15) means an
  operator could enable one without the other — this is intentional
  (distinct calling contexts) but should be clearly documented in
  `config/config.yaml`'s inline comments (Section 13 already
  includes this).

## 23. Future extensions

- EP-083–EP-086 are expected to reuse `ProviderRequestExecutor` for
  their own modality's provider execution rather than each
  re-implementing fallback/retry.
- EP-087 will need a single place that knows about every modality's
  entry point (`TextGenerationService` among them) — out of scope
  here, left to that EP's own STEP 1.

## 24. Open questions (non-blocking)

- Exact internal naming for `ProviderRequestExecutor`'s outcome type
  (Section 14) is a STEP 2 implementation detail and does not affect
  architecture.

---

# 25. Quality Gate

### Target correctness
- [x] Target EP matches `TARGET_EP` (EP-082)
- [x] Target exists in canonical roadmap (`JARVIS_ROADMAP.md` Phase C, detailed in `docs/BACKLOG.md`)
- [x] No automatic EP substitution occurred

### Architecture
- [x] Existing architecture inspected (`src/core/ai/*`, `src/services/ai_service.py`, `src/skills/reflection`, `src/skills/prompt_optimizer`)
- [x] Relevant existing functionality identified (Section 5)
- [x] Dependencies documented (Section 10)
- [x] Boundaries documented (Section 7)
- [x] Contracts documented (Section 12, 14)
- [x] Security considered (Section 16)
- [x] Error handling considered (Section 17)
- [x] Testing strategy defined (Section 18)

### Scope
- [x] IN SCOPE defined
- [x] OUT OF SCOPE defined
- [x] DEFERRED defined
- [x] No unnecessary scope expansion

### Implementation readiness
- [x] STEP 2 can implement without architectural guessing
- [x] Expected file impact documented (Section 26)
- [x] Parallel-development risks documented (Section 21)
- [x] Backward compatibility considered (Section 19)

### Safety
- [x] No production code implemented
- [x] No tests implemented
- [x] No unrelated refactoring performed
- [x] No unrelated files modified

---

## 26. File impact (approved)

| File | Change | Reason |
|---|---|---|
| `src/services/ai_service.py` | MODIFY | `ask()` calls the shared `ProviderRequestExecutor` instead of its own inline loop; public contract unchanged (Section 19). |
| `src/core/ai/provider_request_executor.py` | CREATE | New shared fallback/retry executor (Section 11.2). |
| `src/services/text_generation_service.py` | CREATE | EP-082's standalone content-generation entry point (Section 11.1). |
| `src/core/ai/provider.py` | MODIFY | Additive `temperature`/`system_prompt` kwargs on `AIProvider.ask()` (Section 12). |
| `src/core/ai/claude_provider.py` | MODIFY | Honor new optional kwargs when provided; unchanged otherwise. |
| `src/core/ai/providers/gemini_provider.py` | MODIFY | Same as above. |
| `src/bootstrap.py` | MODIFY | Dependency wiring for `ProviderRequestExecutor`/`TextGenerationService` only — no CLI/CommandRouter registration. |
| `config/config.yaml` | MODIFY | New additive `content_generation:` section (Section 13); `ai:`/`providers:` unchanged. |
| `tests/EP082/` | CREATE | New test suite (Section 18). |
| `docs/architecture/designs/EP082_DESIGN.md` | MODIFY | This document (already updated). |

`CommandRouter` and its module registrations are explicitly NOT in
this list (Decision 2). No other file is expected to change in
STEP 2.

---

# 27. Final STEP 1 Report

```text
TARGET EP: EP-082
OFFICIAL NAME: Text Generation Provider Integration

STATUS:
STEP 1 — APPROVED / READY FOR STEP 2

OWNER DECISIONS:
1. Shared fallback/retry executor — APPROVED (ProviderRequestExecutor)
2. CLI namespace — DEFERRED
3. Configuration namespace — APPROVED: content_generation:

ARCHITECTURE:
- TextGenerationService is standalone and non-conversational.
- Shared ProviderRequestExecutor owns provider request retry/fallback execution.
- ProviderManager remains responsible for provider management and candidate ordering.
- AIService.ask() uses the shared executor with behavior preserved.
- AIProvider receives additive temperature/system_prompt overrides.

CONTRACTS:
- TextGenerationResult contract clarified.
- Failure semantics clarified.
- temperature semantics clarified.
- system_prompt semantics clarified.

BACKWARD COMPATIBILITY:
AIService.ask() behavior and public contract remain unchanged.

IMPLEMENTATION:
No implementation performed.

FILES MODIFIED:
docs/architecture/designs/EP082_DESIGN.md only.

FILES NOT MODIFIED:
All production code, tests, configuration, bootstrap, CommandRouter, and EP-069 implementation.

STEP 2:
READY TO BEGIN.

GIT:
No Git operations performed.
```

```text
STEP 1 COMPLETE.
No implementation was performed.
STEP 2 may begin.
```
